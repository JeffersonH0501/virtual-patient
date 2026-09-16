"""OpenFace 3.0 raw visual feature extraction for interview turns.

This module replaces the previous Py-Feat visual extractor. It is
extraction-and-quality only: it runs OpenFace 3.0 (RetinaFace face detection,
STAR 68-point landmarks, and a multitask model for action units and gaze) over
the student video, selects the best face-confidence detection per frame, and
emits raw per-frame series plus frame-level quality for each turn window. It
does NOT derive metrics, apply methodology thresholds, or assign any label. All
derivation (visual alignment against a calibrated center, dwell segmentation,
nod detection, smile activity) lives in ``app/nonverbal/preprocessing.py``.

The emitted signal contract (field names and units) is preserved exactly from
the previous extractor, so downstream preprocessing, calibration, schemas,
thresholds, and UI keep working unchanged. This file hosts the pure OpenFace 3.0
-> Signal_Contract adapter (task 1.1), the module skeleton and public entry
point ``analyze_openface_student_turn_videos`` with its config guard (task 2.1),
the real per-frame OpenFace 3.0 inference body (video decode, per-frame model
inference on CPU, best-face selection; task 2.2), and the turn-window assembly
``_raw_features_for_turn`` (equivalent to the previous extractor).

OpenFace 3.0 API used (openface-test 0.1.26)
--------------------------------------------
The per-frame turn path drives the two components it needs
(``openface.face_detection.FaceDetector`` and
``openface.multitask_model.MultitaskPredictor``), following the package's own
``openface.demo.process_video`` reference flow but omitting the STAR
``openface.landmark_detection.LandmarkDetector`` (the turn path emits no
landmarks; see below):

* ``FaceDetector.get_face(image_path)`` runs RetinaFace over an image **read
  from a file path** (``cv2.imread`` internally) and returns
  ``(cropped_first_face, dets)`` where ``dets`` is an ``ndarray`` of rows
  ``[x1, y1, x2, y2, confidence, *retinaface_5pt_landmarks]``. Because the
  detector decodes from a path, each sampled frame is written to a short-lived
  temporary image and removed immediately (nothing is persisted), matching the
  single-image debug extractor.
* The highest-confidence detection row is selected (``det[4]`` is the RetinaFace
  confidence), its face box is cropped from the frame, and
  ``MultitaskPredictor.predict(cropped_face)`` returns
  ``(emotion_logits, gaze_output, au_output)``. Only ``gaze_output`` (a
  ``(1, 2)`` tensor of ``[yaw, pitch]`` in radians) and ``au_output`` (the
  multitask AU head) are read; the emotion logits are dropped at this boundary
  (see below). The STAR ``LandmarkDetector`` is **not** constructed or exercised
  by the turn path, which emits no landmarks; landmarks (and the STAR model) are
  produced only by the debug path.

Runs on CPU only (Req 6.3, 6.4): the models are constructed with
``device="cpu"`` and cached once at module level. There is no CUDA code path and
no CUDA-to-CPU fallback.

The raw output maps cleanly to ``app.multimodal.schemas.NonverbalRawFeatures``
and is descriptive-only: it represents behavioural and contextual observations,
not empathy, attention, warmth, or any psychological state.

Descriptive-only / emotion boundary
------------------------------------
OpenFace 3.0's multitask model also produces an emotion-recognition output.
That output is discarded at the boundary between the model and this module's
data model: :class:`OpenFaceFaceObservation` deliberately has **no emotion
field**, so the adapter cannot accept, track, derive from, or log emotion, and
no internal processing can depend on it (preserving the Descriptive_Contract).
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.multimodal.schemas import NonverbalRawFeatures


logger = logging.getLogger(__name__)

# Extractor identity metadata (Req 5.1). Persisted in the ``extractor`` block so
# results stay traceable to OpenFace 3.0.
EXTRACTOR_NAME = "openface"
EXTRACTOR_VERSION = "3.0"

# Descriptive detector id reported in the ``extractor`` metadata block.
DETECTOR_NAME = "openface3-multitask"

# Writable weights volume mount point (Req 6.2). Weights are materialized here at
# first run, never into site-packages or the repository.
WEIGHTS_ROOT = Path("/app/openface/weights")

# Sampling and per-frame inference configuration.
# 10 FPS gives enough temporal resolution to see a head-nod oscillation
# (~0.5-1 s per nod => ~5-10 samples) while keeping CPU cost lower than 15 FPS.
# Gaze and smile also benefit from the extra samples; their contract is unchanged.
SAMPLE_FPS = 10.0
BATCH_SIZE = 1  # per-frame path; retained for contract stability (Req 5.2)
FACE_DETECTION_THRESHOLD = 0.5  # unchanged best-face detection gate

# This initial version runs OpenFace 3.0 inference on CPU only. There is no CUDA
# code path and no CUDA-to-CPU fallback (Req 6.3, 6.4).
DEVICE = "cpu"

# Hugging Face repository and weight file names published by the OpenFace 3.0
# package (see ``openface.cli`` / ``openface.demo``). Weights are materialized
# into ``WEIGHTS_ROOT`` at first run and never into site-packages or the repo.
WEIGHTS_HF_REPO_ID = "nutPace/openface_weights"
RETINAFACE_WEIGHTS_FILENAME = "Alignment_RetinaFace.pth"
LANDMARK_WEIGHTS_FILENAME = "Landmark_98.pkl"
MULTITASK_WEIGHTS_FILENAME = "MTL_backbone.pth"

# Index of AU12 (lip-corner puller) within the multitask AU head's 8-value
# output vector. The OpenFace 3.0 MTL model (``openface.model.MTL``) is built
# with ``au_numbers=8`` and does not expose the AU labels in code.
# TODO(verify): confirm this index against the OpenFace 3.0 weights/model card
# for the exact 8-AU ordering; the upstream multitask AU set is documented as
# [AU1, AU2, AU4, AU6, AU12, AU15, AU20, AU25], placing AU12 at index 4. If the
# published ordering differs, only this constant needs to change.
AU12_INDEX = 4


class OpenFaceExtractionError(RuntimeError):
    """Raised when the OpenFace 3.0 turn extractor cannot run.

    Covers a non-writable weights volume (Req 6.9), a failed model
    import/construction, and an unusable video frame rate. The message names
    OpenFace so operators can act on it directly.
    """


def _validate_extractor_config(
    *,
    sample_fps: float = SAMPLE_FPS,
    batch_size: int = BATCH_SIZE,
    face_detection_threshold: float = FACE_DETECTION_THRESHOLD,
) -> None:
    """Validate the effective extractor configuration, rejecting bad values.

    Guards the values that actually drive extraction (the module constants plus
    any injected overrides), not just the defaults, so an invalid override cannot
    silently produce a degenerate sampling stride, an empty batch, or a
    non-sensical detection gate. A zero or non-positive value for any of
    ``sample_fps``, ``batch_size``, or ``face_detection_threshold`` is rejected
    with a clear :class:`ValueError` rather than accepted (Req 5.6).

    Invoked at extractor first use (from
    :func:`analyze_openface_student_turn_videos`) so the validation runs against
    the configuration each extraction actually uses.
    """
    if not (isinstance(sample_fps, (int, float)) and math.isfinite(sample_fps)) or sample_fps <= 0:
        raise ValueError(f"sample_fps must be > 0, got {sample_fps!r}")
    if not (isinstance(batch_size, int) and not isinstance(batch_size, bool)) or batch_size <= 0:
        raise ValueError(f"batch_size must be > 0, got {batch_size!r}")
    if (
        not (
            isinstance(face_detection_threshold, (int, float))
            and math.isfinite(face_detection_threshold)
        )
        or face_detection_threshold <= 0
    ):
        raise ValueError(
            f"face_detection_threshold must be > 0, got {face_detection_threshold!r}"
        )


@dataclass(frozen=True)
class OpenFaceFaceObservation:
    """One detected face from OpenFace 3.0 for a single frame (raw model output).

    This carries only the raw model outputs the Signal_Contract needs. It has
    **no emotion field** on purpose: OpenFace 3.0's emotion-recognition output is
    discarded at the model boundary and never enters this data model, so nothing
    downstream can accept, track, derive from, or log it (Req 4.6, 4.8).

    Attributes
    ----------
    detection_confidence:
        RetinaFace detection confidence for this face. Only its ordering is used
        downstream (best-face selection and validity), so any finite score whose
        ordering matches "more confident = higher" is acceptable.
    gaze:
        OpenFace 3.0 gaze output. Either a pair/sequence of angles
        ``(yaw, pitch)`` (radians or degrees) or a direction vector with at least
        a horizontal and a vertical component. See :func:`adapt_face_observation`
        for the exact component-to-axis assignment.
    head_pose:
        OpenFace 3.0 head-pose output as ``(pitch, yaw, roll)`` angles. See
        :func:`adapt_face_observation` for the unit/sign convention.
    au12_activation:
        OpenFace 3.0 AU12 (lip-corner puller) activation, or ``None`` when the AU
        head produced no usable value for this face.
    landmarks_xy:
        STAR 68-point landmarks as ``[x, y]`` image-pixel pairs, or ``None`` when
        landmarks are unavailable. Consumed only by the debug path.
    """

    detection_confidence: float
    gaze: Any
    head_pose: Any
    au12_activation: float | None
    landmarks_xy: list[list[float]] | None


def adapt_face_observation(obs: OpenFaceFaceObservation) -> dict[str, Any]:
    """Convert one OpenFace 3.0 face observation to the existing candidate dict.

    Returns the candidate dict keys consumed by the turn extractor and the debug
    path::

        {face_score, gaze_yaw, gaze_pitch, au12, head_pitch, head_yaw, head_roll}

    Every value is a finite ``float`` or ``None``; a value that is missing,
    non-numeric, or non-finite is emitted as ``None`` rather than fabricated
    (Req 2.9, 4.2). This function is pure and unit-testable in isolation, with no
    dependency on the OpenFace 3.0 model being importable.

    Conversions (Req 2.3, 2.4, 2.5, 2.6, 2.8)
    -----------------------------------------
    face_score
        Monotonic pass-through of the RetinaFace ``detection_confidence``. Only
        the ordering is used downstream (argmax for best-face selection, and
        ``face_score is not None`` for validity counting), so no scale change is
        applied beyond guaranteeing a finite float (Req 2.6).

    gaze_yaw / gaze_pitch
        Emitted in **radians** with a fixed sign convention. Preprocessing
        measures gaze deviation relative to a calibrated center
        (``hypot(gaze_yaw - center_yaw, gaze_pitch - center_pitch)``), and the
        **same adapter runs for both the calibration recording and the interview
        turns**, so any fixed sign choice cancels in that relative measure. Two
        invariants are preserved: (1) the output is in radians (so
        ``alignment_tolerance_radians`` keeps its meaning), and (2) the
        horizontal/vertical sign is consistent across both extraction paths.

        Component-to-axis assignment (fixed once, reused identically in
        calibration): when ``obs.gaze`` is a vector of length >= 2, the
        horizontal component ``x = gaze[0]`` and the vertical component
        ``y = gaze[1]`` are converted to angles with ``atan2`` against the depth
        component ``z = gaze[2]`` when present (else against ``1.0``):

            gaze_yaw   = atan2(x, z)   # horizontal, sign: +x -> +yaw
            gaze_pitch = atan2(y, z)   # vertical,   sign: +y -> +pitch

        When ``obs.gaze`` is a pair of scalar angles ``(a0, a1)``, they are taken
        as ``(yaw, pitch)`` already; values are treated as radians (OpenFace 3.0
        gaze angles are radians). No degree conversion is applied to angle-pair
        gaze because the toolkit reports gaze angles in radians.

    head_pitch / head_yaw / head_roll
        Emitted in the **existing angular unit: degrees, +up convention**
        (matching the previous Py-Feat ``Pitch/Yaw/Roll`` facepose and the
        ``min_amplitude_deg`` naming in preprocessing). Nod detection uses only
        the relative pitch oscillation amplitude and calibration uses the median
        per axis, so both are invariant to a constant offset but **not** to a
        unit change or a sign flip; the adapter therefore fixes the unit to
        degrees and preserves the ``(pitch, yaw, roll)`` axis order and sign of
        the OpenFace 3.0 head-pose output without remapping axes (Req 2.4, 2.8).

    au12
        The AU12 (lip-corner puller) activation is mapped monotonically onto the
        existing ``au12`` scale as a finite float. Preprocessing takes the mean
        over valid frames and compares against a (currently unset) threshold, so
        a monotonic, finite activation preserves that meaning. No numeric
        equivalence to Py-Feat's AU12 is claimed (Req 2.5, 2.8).

    Emotion is never accepted, read, tracked, derived from, or logged here: it is
    absent from :class:`OpenFaceFaceObservation` by design (Req 4.6, 4.8).
    """
    gaze_yaw, gaze_pitch = _adapt_gaze(obs.gaze)
    head_pitch, head_yaw, head_roll = _adapt_head_pose(obs.head_pose)
    return {
        "face_score": _finite_float(obs.detection_confidence),
        "gaze_yaw": gaze_yaw,
        "gaze_pitch": gaze_pitch,
        "au12": _finite_float(obs.au12_activation),
        "head_pitch": head_pitch,
        "head_yaw": head_yaw,
        "head_roll": head_roll,
    }


def _adapt_gaze(gaze: Any) -> tuple[float | None, float | None]:
    """Map an OpenFace 3.0 gaze output onto ``(gaze_yaw, gaze_pitch)`` radians.

    Supports two shapes (see :func:`adapt_face_observation` for the fixed
    convention):

    * A direction vector of length >= 2: yaw/pitch are derived with ``atan2`` on
      the horizontal/vertical components against the depth component (or ``1.0``
      when absent).
    * A pair of scalar gaze angles ``(yaw, pitch)`` already in radians.

    Returns ``(None, None)`` when the gaze output is missing or unusable.
    """
    components = _as_float_sequence(gaze)
    if components is None or len(components) < 2:
        return None, None

    horizontal = components[0]
    vertical = components[1]
    if horizontal is None or vertical is None:
        return None, None

    if len(components) >= 3 and components[2] is not None:
        # Direction vector: convert to angles about the depth axis.
        depth = components[2]
        gaze_yaw = _finite_float(math.atan2(horizontal, depth))
        gaze_pitch = _finite_float(math.atan2(vertical, depth))
        return gaze_yaw, gaze_pitch

    # Exactly two usable components: treat them as (yaw, pitch) angles already in
    # radians, the unit OpenFace 3.0 reports gaze angles in.
    return _finite_float(horizontal), _finite_float(vertical)


def _adapt_head_pose(head_pose: Any) -> tuple[float | None, float | None, float | None]:
    """Map an OpenFace 3.0 head-pose output onto ``(head_pitch, head_yaw, head_roll)``.

    The output is taken as ``(pitch, yaw, roll)`` in degrees with the existing
    +up sign convention; the axis order and sign are preserved (no remap).
    Returns ``None`` for any component that is missing or non-finite.
    """
    components = _as_float_sequence(head_pose)
    if components is None or len(components) < 3:
        return None, None, None
    return components[0], components[1], components[2]


def _as_float_sequence(value: Any) -> list[float | None] | None:
    """Coerce a vector-like value to a list of finite floats / ``None`` entries.

    Accepts lists, tuples, or any non-string iterable (e.g. a NumPy array).
    Returns ``None`` when the value is not a usable sequence.
    """
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        items = list(value)
    except TypeError:
        return None
    return [_finite_float(item) for item in items]


def _finite_float(value: Any) -> float | None:
    """Return ``value`` as a finite ``float`` or ``None`` when not convertible."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# OpenFace 3.0's STAR landmark model is trained on WFLW and emits 98 points per
# face (not the classic 68). The debug overlay renders whatever points are
# present, in order, so the pairing helper is point-count agnostic and does not
# force a specific count; this is the native STAR count for reference only.
STAR_LANDMARK_POINT_COUNT = 98


def pair_star_landmarks(landmarks: Any) -> list[list[float]] | None:
    """Map an OpenFace 3.0 STAR landmark output to ``[x, y]`` pixel pairs.

    This replaces Py-Feat's dynamic ``x_<n>``/``y_<n>`` column discovery: instead
    of scanning for per-point columns, it reads OpenFace 3.0's landmark array
    directly and pairs coordinates **in point order** (point 0 first). The result
    is the ``landmarks`` field of the debug contract, rendered by the UI overlay
    as image-pixel coordinates without any coordinate reinterpretation; the
    overlay draws each point independently, so it does not assume a fixed point
    count (Req 2.2, 8.4).

    OpenFace 3.0's STAR model emits the 98-point WFLW landmark set (see
    :data:`STAR_LANDMARK_POINT_COUNT`), so the pairing is **count-agnostic**: it
    returns as many ``[x, y]`` pairs as the model produced rather than forcing a
    specific number. No point is fabricated or dropped to hit a target count.

    Accepted input shapes:

    * A sequence of ``(x, y)`` pairs (list/tuple of length-2 items).
    * A NumPy-like array of shape ``(N, 2)`` (any non-string iterable of
      length-2 rows is accepted, so a 2-D ``ndarray`` iterates into rows).
    * A flat sequence of ``2 * N`` values ordered ``[x0, y0, x1, y1, ...]``.

    This helper is pure and unit-testable in isolation: it has no dependency on
    the OpenFace 3.0 model being importable and reuses :func:`_as_float_sequence`
    and :func:`_finite_float` for coercion.

    Returns
    -------
    list[list[float]] | None
        The ``[x, y]`` float pairs in point order, or ``None`` when the landmarks
        are missing, empty, oddly shaped, or contain a coordinate that is not a
        finite number. Missing or malformed landmarks are reported as unavailable
        rather than fabricated (Descriptive_Contract).
    """
    if landmarks is None or isinstance(landmarks, (str, bytes)):
        return None
    try:
        rows = list(landmarks)
    except TypeError:
        return None
    if not rows:
        return None

    # Shape (N, 2) or a sequence of N [x, y] pairs: each row is a length-2
    # coordinate. Detect this by inspecting the first row; a flat coordinate
    # sequence has scalar (non-iterable) entries instead.
    if _is_pair_like(rows[0]):
        pairs: list[list[float]] = []
        for row in rows:
            coords = _as_float_sequence(row)
            if coords is None or len(coords) != 2:
                return None
            x, y = coords[0], coords[1]
            if x is None or y is None:
                return None
            pairs.append([x, y])
        return pairs

    # Otherwise treat it as a flat [x0, y0, x1, y1, ...] sequence of an even
    # number of values (2 per point). An odd length is malformed.
    flat = _as_float_sequence(landmarks)
    if flat is None or len(flat) == 0 or len(flat) % 2 != 0:
        return None
    pairs = []
    for index in range(0, len(flat), 2):
        x = flat[index]
        y = flat[index + 1]
        if x is None or y is None:
            return None
        pairs.append([x, y])
    return pairs


def _is_pair_like(value: Any) -> bool:
    """Return ``True`` when ``value`` is a non-string iterable (a coordinate row).

    Used to distinguish a sequence of ``[x, y]`` pairs / an ``(N, 2)`` array from
    a flat ``[x0, y0, ...]`` sequence of scalars.
    """
    if value is None or isinstance(value, (str, bytes)):
        return False
    try:
        iter(value)
    except TypeError:
        return False
    return True


@dataclass(frozen=True)
class StudentTurnVideo:
    """A conversation-turn window analyzed against the student video.

    Shape preserved unchanged from the previous extractor so the pipeline and
    calibration call sites keep constructing it the same way.
    """

    turn_id: str
    start_ms: int
    end_ms: int
    conversation_speaker: str = "unknown"


def analyze_openface_student_turn_videos(
    video_path: Path,
    turns: Iterable[StudentTurnVideo],
) -> dict[str, dict[str, Any]]:
    """Produce raw OpenFace 3.0 per-frame series over the common turn windows.

    Returns a mapping ``turn_id -> raw features dict`` where each value serializes
    a :class:`NonverbalRawFeatures` (via ``model_dump``) with an added
    ``observationContext`` block. No derived metrics or labels are produced.

    This preserves the public contract of the previous
    ``analyze_pyfeat_student_turn_videos`` entry point exactly (same signature and
    same return shape), swapping the extractor identity and the inference backend
    to OpenFace 3.0.

    The extractor configuration is validated on first use (Req 5.6) before any
    frame is sampled, so an invalid ``sample_fps``/``batch_size``/detection
    threshold is rejected up front rather than producing a degenerate stride, an
    empty batch, or a non-sensical detection gate.
    """
    _validate_extractor_config()

    turn_list = list(turns)
    if not turn_list:
        return {}

    rows = _sample_best_face_rows(video_path)

    return {
        turn.turn_id: {
            **_raw_features_for_turn(
                [
                    row
                    for row in rows
                    if turn.start_ms <= row["timestamp_ms"] <= turn.end_ms
                ],
                turn,
            ).model_dump(),
            "observationContext": {
                "observedParticipant": "student",
                "conversationSpeaker": turn.conversation_speaker,
            },
        }
        for turn in turn_list
    }


# One shared OpenFace 3.0 model bundle, constructed lazily and cached at module
# level so weights load once. Construction and inference are serialized because
# the underlying PyTorch models are not guaranteed thread-safe and CPU inference
# is fine running serialized here.
_models: "_OpenFaceModels | None" = None
_models_lock = threading.Lock()


@dataclass(frozen=True)
class _OpenFaceModels:
    """The OpenFace 3.0 components used by the per-frame turn path.

    The turn path drives RetinaFace detection, the STAR landmark detector, and
    the multitask AU/gaze head. The STAR landmarks are used to derive the head
    pose (pitch/yaw/roll) via PnP so head nods can be detected; OpenFace 3.0 does
    not provide head pose directly.
    """

    face_detector: Any
    landmark_detector: Any
    multitask_model: Any


def _assert_weights_root_writable() -> None:
    """Fail fast when :data:`WEIGHTS_ROOT` exists but cannot be written (Req 6.9).

    This is the authoritative writability guard for the weights-materialization
    boundary. ``os.access(..., os.W_OK)`` is a fast pre-check, but it is not
    reliable on its own: it can report a directory writable that a subsequent
    write would fail (for example when running as ``root``, which bypasses the
    directory's permission bits on many filesystems), which would let a
    non-writable mount slip through into a confusing download failure instead of
    a clear one. So the guard also performs an actual write probe (create and
    remove a temporary file). Either check failing raises
    :class:`OpenFaceExtractionError` with the same clear, actionable message the
    design specifies, rather than degrading to a read-only or ``site-packages``
    path.

    Shared, side-effect-free helper (beyond the transient probe file): both the
    turn path (via :func:`_materialize_weights`) and the debug path (task 4.1)
    reuse this guard so a non-writable volume fails fast identically in both.
    The turn path lets the error propagate; the debug path wraps it as
    ``OpenFaceDebugUnavailable`` (see the design's Error Handling section).
    """
    not_writable = (
        f"OpenFace 3.0 weights directory {WEIGHTS_ROOT.parent} is not "
        "writable; fix the mount permissions"
    )
    if not os.access(WEIGHTS_ROOT, os.W_OK):
        raise OpenFaceExtractionError(not_writable)

    probe = WEIGHTS_ROOT / ".openface_write_probe"
    try:
        probe.touch()
    except OSError as error:
        raise OpenFaceExtractionError(f"{not_writable} ({error})") from error
    finally:
        try:
            probe.unlink()
        except OSError:
            # The probe may already be gone or unremovable; that does not change
            # the writability decision already made above.
            pass


def _materialize_weights() -> Path:
    """Ensure the OpenFace 3.0 weights exist under :data:`WEIGHTS_ROOT`.

    Creates the writable weights directory and downloads the published weight
    files once (mirroring the package's own Hugging Face download). If the
    mounted weights volume exists but is **not writable**, fails fast with a
    clear, OpenFace-named error rather than continuing into broken model
    construction or degrading to a read-only / site-packages path (Req 6.2,
    6.9). Never writes into site-packages or the repository.
    """
    try:
        WEIGHTS_ROOT.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as error:
        raise OpenFaceExtractionError(
            f"OpenFace 3.0 weights directory {WEIGHTS_ROOT.parent} is not "
            f"writable; fix the mount permissions ({error})"
        ) from error
    _assert_weights_root_writable()

    required = (
        RETINAFACE_WEIGHTS_FILENAME,
        LANDMARK_WEIGHTS_FILENAME,
        MULTITASK_WEIGHTS_FILENAME,
    )
    if all((WEIGHTS_ROOT / name).exists() for name in required):
        return WEIGHTS_ROOT

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=WEIGHTS_HF_REPO_ID,
            local_dir=str(WEIGHTS_ROOT),
            repo_type="model",
        )
    except (PermissionError, OSError) as error:
        raise OpenFaceExtractionError(
            f"OpenFace 3.0 weights directory {WEIGHTS_ROOT.parent} is not "
            f"writable; fix the mount permissions ({error})"
        ) from error
    except Exception as error:  # noqa: BLE001 - surface any download failure clearly
        raise OpenFaceExtractionError(
            f"OpenFace 3.0 weights could not be materialized under "
            f"{WEIGHTS_ROOT}: {error}"
        ) from error
    return WEIGHTS_ROOT


@contextlib.contextmanager
def _working_directory(path: Path):
    """Temporarily change the process working directory, always restoring it.

    Used only around OpenFace 3.0 model construction so the RetinaFace backbone's
    hardcoded relative pretrain path resolves into the writable weights volume.
    Serialized by the caller's construction lock, so the transient global CWD
    change does not race other extractor work.
    """
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# Writable directory (inside the weights volume) that replaces STAR's hardcoded
# ``/work/...`` training checkpoint/log path. Only its ``log``/``model`` subdirs
# are touched by the TensorBoard writer opened during STAR construction; the
# landmark inference itself does not depend on this location.
_STAR_RUNTIME_DIR = WEIGHTS_ROOT.parent / "star_runtime"

_star_logdir_redirected = False


def _redirect_star_logdir() -> None:
    """Point STAR's config log/work dirs at a writable path (idempotent).

    OpenFace 3.0's STAR ``Alignment`` config hardcodes
    ``ckpt_dir = '/work/jiewenh/openFace/OpenFace-3.0/STAR'`` and, in
    ``init_instance``, opens a TensorBoard ``SummaryWriter`` under
    ``<ckpt_dir>/<data>/<folder>/log``. In the container that path is not
    writable (the process runs as a non-root user), so constructing the STAR
    ``LandmarkDetector`` raises ``PermissionError: '/work'``. This wraps
    ``Base.init_instance`` to rewrite ``work_dir``/``model_dir``/``log_dir`` onto
    the writable weights volume just before the writer is created. It is a
    runtime, in-process shim on the installed package's behaviour (no edit to
    ``site-packages`` on disk, no parallel environment) and is a no-op after the
    first call. Shared by the turn extractor and the debug path.
    """
    global _star_logdir_redirected
    if _star_logdir_redirected:
        return
    try:
        from openface.STAR.conf.base import Base
    except Exception as error:  # noqa: BLE001 - report uniformly
        raise OpenFaceExtractionError(
            f"OpenFace 3.0 STAR config import failed: {error}"
        ) from error

    _STAR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    original_init_instance = Base.init_instance

    def _patched_init_instance(self: Any) -> Any:
        # Redirect the training-log locations onto the writable volume before the
        # writer / file handler are opened. Inference does not use these.
        self.work_dir = str(_STAR_RUNTIME_DIR)
        self.model_dir = str(_STAR_RUNTIME_DIR / "model")
        self.log_dir = str(_STAR_RUNTIME_DIR / "log")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.model_dir, exist_ok=True)
        return original_init_instance(self)

    Base.init_instance = _patched_init_instance
    _star_logdir_redirected = True


def _get_models() -> _OpenFaceModels:
    """Lazily construct and cache the OpenFace 3.0 models on CPU.

    Weights are materialized first (failing fast on a non-writable volume), then
    the three components are built with ``device="cpu"`` and cached. Any
    import/construction failure surfaces as :class:`OpenFaceExtractionError`
    (there is no CUDA path to try).
    """
    global _models
    if _models is not None:
        return _models
    with _models_lock:
        if _models is not None:
            return _models
        weights_root = _materialize_weights()
        try:
            from openface.face_detection import FaceDetector
            from openface.landmark_detection import LandmarkDetector
            from openface.multitask_model import MultitaskPredictor
        except Exception as error:  # noqa: BLE001 - report any import failure uniformly
            raise OpenFaceExtractionError(
                f"OpenFace 3.0 import failed: {error}"
            ) from error
        # STAR's config hardcodes a training checkpoint path ('/work/...') and,
        # on construction, opens a TensorBoard writer under it, which fails with
        # PermissionError in the container. Redirect STAR's log/work directories
        # into the writable weights volume before building the landmark detector.
        _redirect_star_logdir()
        try:
            # RetinaFace's backbone loads its MobileNet pretrain from the
            # hardcoded relative path ``./weights/mobilenetV1X0.25_pretrain.tar``
            # (``openface.Pytorch_Retinaface.models.retinaface``), resolved
            # against the process working directory. That backbone file is part
            # of the materialized weights snapshot, so construction runs with the
            # working directory temporarily set to ``WEIGHTS_ROOT.parent`` so the
            # relative ``./weights/...`` resolves into the writable weights volume
            # rather than the app root. Nothing is written to site-packages or the
            # repository; the working directory is always restored.
            with _working_directory(WEIGHTS_ROOT.parent):
                _models = _OpenFaceModels(
                    face_detector=FaceDetector(
                        model_path=str(weights_root / RETINAFACE_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                    landmark_detector=LandmarkDetector(
                        model_path=str(weights_root / LANDMARK_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                    multitask_model=MultitaskPredictor(
                        model_path=str(weights_root / MULTITASK_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                )
        except Exception as error:  # noqa: BLE001 - construction may fail on bad weights
            raise OpenFaceExtractionError(
                f"OpenFace 3.0 model construction failed: {error}"
            ) from error
    return _models


def _sample_best_face_rows(video_path: Path) -> list[dict[str, Any]]:
    """Sample the video and return the best-face candidate dict per sampled frame.

    Each returned row is the candidate dict produced by
    :func:`adapt_face_observation` augmented with a ``timestamp_ms`` key, i.e.::

        {timestamp_ms, face_score, gaze_yaw, gaze_pitch, au12,
         head_pitch, head_yaw, head_roll}

    Real per-frame OpenFace 3.0 extraction (Req 1.6): the video is opened with
    OpenCV, ``source_fps`` is read, and every ``skip_frames``-th frame is run
    through the OpenFace 3.0 pipeline on CPU. For each sampled frame the
    highest-confidence RetinaFace detection is kept (Req 3.2) and mapped to the
    candidate dict via :func:`adapt_face_observation`; the per-frame timestamp is
    ``round(frame_index * 1000 / source_fps)`` ms (Req 3.3). The emotion output
    is dropped at the model boundary and never enters an
    :class:`OpenFaceFaceObservation` (Req 4.8). Frames with no detection are
    omitted from the returned rows and reappear as reduced ``valid_frame_count``
    in the turn assembly, never as fabricated values (Req 4.1, 4.2).
    """
    import cv2

    models = _get_models()

    capture = cv2.VideoCapture(str(video_path))
    try:
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        if not source_fps or not math.isfinite(source_fps) or source_fps <= 0:
            raise OpenFaceExtractionError(
                "Unable to determine video frame rate for OpenFace 3.0"
            )
        skip_frames = max(round(source_fps / SAMPLE_FPS), 1)

        rows: list[dict[str, Any]] = []
        frame_index = 0
        while True:
            grabbed, frame = capture.read()
            if not grabbed:
                break
            if frame_index % skip_frames == 0:
                observation = _observe_best_face(models, frame, cv2)
                if observation is not None:
                    candidate = adapt_face_observation(observation)
                    candidate["timestamp_ms"] = round(frame_index * 1000 / source_fps)
                    rows.append(candidate)
            frame_index += 1
        return rows
    finally:
        capture.release()


def _observe_best_face(
    models: _OpenFaceModels,
    frame: Any,
    cv2: Any,
) -> OpenFaceFaceObservation | None:
    """Run OpenFace 3.0 on one frame and return the best-confidence observation.

    Returns ``None`` when no face passes detection. The OpenFace 3.0 detector
    decodes from a file path, so the already-decoded frame is written to a
    short-lived temporary image and removed immediately (nothing is persisted).
    Only detection confidence, gaze, and AU12 are read from the model output;
    the emotion logits returned by the multitask model are **dropped here** and
    never assigned, tracked, derived from, or logged (Req 4.8). Head pose and
    landmarks are not produced by the multitask/turn path and are left
    unavailable (``None``).
    """
    detections = _detect_faces(models.face_detector, frame, cv2)
    if detections is None or len(detections) == 0:
        return None

    best_det = max(detections, key=lambda det: _finite_float(det[4]) or -math.inf)
    confidence = _finite_float(best_det[4])
    if confidence is None:
        return None

    crop = _crop_face(frame, best_det)
    if crop is None or crop.size == 0:
        return None

    try:
        # The multitask model returns (emotion_logits, gaze_output, au_output).
        # The emotion logits are intentionally discarded at this boundary
        # (Descriptive_Contract, Req 4.8): they are never bound to a named
        # variable used downstream.
        _, gaze_output, au_output = models.multitask_model.predict(crop)
    except Exception as error:  # noqa: BLE001 - a per-frame inference fault omits the frame
        logger.warning(
            "openface_frame_inference_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None

    # STAR landmarks (full-image pixel coords) drive the PnP head-pose estimate
    # used for nod detection, since OpenFace 3.0 does not output head pose.
    landmarks_xy = _detect_landmarks_xy(models.landmark_detector, frame, best_det)
    height, width = int(frame.shape[0]), int(frame.shape[1])
    head_pitch, head_yaw, head_roll = _head_pose_from_landmarks(
        landmarks_xy, width, height
    )

    return OpenFaceFaceObservation(
        detection_confidence=confidence,
        gaze=_gaze_pair(gaze_output),
        head_pose=(head_pitch, head_yaw, head_roll),
        au12_activation=_au12_activation(au_output),
        landmarks_xy=landmarks_xy,
    )


def _detect_landmarks_xy(
    landmark_detector: Any, frame: Any, det: Any
) -> list[list[float]] | None:
    """Run STAR landmark detection for one detection, returning ``[x, y]`` pairs.

    ``LandmarkDetector.detect_landmarks(image, dets)`` returns one landmark set
    per detection in full-image pixel coordinates; a single detection is passed
    so one set is returned. Returns ``None`` when landmarks are unavailable, so
    head pose (and the debug overlay) degrade to unavailable rather than being
    fabricated.
    """
    try:
        import numpy as np

        results = landmark_detector.detect_landmarks(frame, np.asarray([det]))
    except Exception as error:  # noqa: BLE001 - landmark fault -> unavailable, not fatal
        logger.warning(
            "openface_landmarks_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None
    try:
        first = results[0]
    except (TypeError, IndexError):
        return None
    return pair_star_landmarks(first)


def _detect_faces(face_detector: Any, frame: Any, cv2: Any) -> Any:
    """Return the RetinaFace detections for ``frame`` as an ``ndarray``.

    ``FaceDetector`` decodes its input from a file path (``cv2.imread``), so the
    frame is written to a short-lived temporary image, detected, and removed
    immediately. Returns ``None`` when detection is unavailable for the frame.
    """
    tmp = tempfile.NamedTemporaryFile(
        prefix="virtual-patient-openface-frame-", suffix=".png", delete=False
    )
    tmp_path = tmp.name
    tmp.close()
    try:
        if not cv2.imwrite(tmp_path, frame):
            return None
        # ``get_face`` returns (cropped_first_face, dets); only ``dets`` (all
        # detections) is needed here so the best-confidence face can be selected
        # and cropped explicitly.
        _, detections = face_detector.get_face(tmp_path)
        return detections
    except Exception as error:  # noqa: BLE001 - a per-frame detection fault omits the frame
        logger.warning(
            "openface_frame_detection_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _crop_face(frame: Any, det: Any) -> Any:
    """Crop the face box ``det[:4]`` from ``frame``, clamped to frame bounds."""
    height = frame.shape[0]
    width = frame.shape[1]
    x1 = max(int(det[0]), 0)
    y1 = max(int(det[1]), 0)
    x2 = min(int(det[2]), width)
    y2 = min(int(det[3]), height)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def _gaze_pair(gaze_output: Any) -> tuple[float, float] | None:
    """Extract ``(yaw, pitch)`` from the multitask gaze output.

    The gaze head returns a ``(1, 2)`` tensor of ``[yaw, pitch]`` in radians
    (see ``openface.demo``: ``gaze_output[0][0]`` / ``gaze_output[0][1]``). The
    values are returned as a plain float pair for :func:`adapt_face_observation`,
    which treats a two-element gaze as ``(yaw, pitch)`` angles already in
    radians. Returns ``None`` when the output is not usable.
    """
    try:
        yaw = _finite_float(gaze_output[0][0])
        pitch = _finite_float(gaze_output[0][1])
    except (TypeError, IndexError, ValueError):
        return None
    if yaw is None or pitch is None:
        return None
    return yaw, pitch


# STAR emits the 98-point WFLW landmark set. These indices pick a stable subset
# for PnP head-pose estimation and their corresponding points on a generic 3D
# face model (in an arbitrary but consistent model space, millimetres). Only the
# RELATIVE head pitch oscillation is used downstream (nod detection) and the
# neutral pose is taken relative to a per-session median, so an approximate
# generic model is adequate — no per-face calibration is claimed.
#   nose tip, chin, left eye outer, right eye outer, left mouth, right mouth
_WFLW_PNP_INDICES = (54, 16, 60, 72, 76, 82)
_PNP_MODEL_POINTS = (
    (0.0, 0.0, 0.0),        # nose tip
    (0.0, -63.6, -12.5),    # chin
    (-43.3, 32.7, -26.0),   # left eye outer corner
    (43.3, 32.7, -26.0),    # right eye outer corner
    (-28.9, -28.9, -24.1),  # left mouth corner
    (28.9, -28.9, -24.1),   # right mouth corner
)


def _head_pose_from_landmarks(
    landmarks_xy: list[list[float]] | None,
    image_width: int,
    image_height: int,
) -> tuple[float | None, float | None, float | None]:
    """Estimate head ``(pitch, yaw, roll)`` in degrees from STAR landmarks via PnP.

    OpenFace 3.0 does not output head pose, so it is derived here: a stable subset
    of the 98-point STAR landmarks is matched against a generic 3D face model and
    ``cv2.solvePnP`` recovers the head rotation, which is converted to Euler
    angles (degrees, +up pitch convention matching the existing series). The
    camera intrinsics are approximated from the image size (focal ~= image width,
    principal point at the image center) since no calibration is available; this
    is adequate because nod detection uses only the RELATIVE pitch oscillation and
    calibration uses the per-axis median as a neutral reference.

    Returns ``(None, None, None)`` when landmarks are missing/malformed or PnP
    fails, so head pose is reported unavailable rather than fabricated.
    """
    if landmarks_xy is None or len(landmarks_xy) <= max(_WFLW_PNP_INDICES):
        return None, None, None
    try:
        import cv2
        import numpy as np

        image_points = np.array(
            [landmarks_xy[i] for i in _WFLW_PNP_INDICES], dtype=np.float64
        )
        if not np.all(np.isfinite(image_points)):
            return None, None, None
        model_points = np.array(_PNP_MODEL_POINTS, dtype=np.float64)

        focal_length = float(image_width)
        camera_matrix = np.array(
            [
                [focal_length, 0.0, image_width / 2.0],
                [0.0, focal_length, image_height / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        ok, rotation_vector, _ = cv2.solvePnP(
            model_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return None, None, None

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        pitch, yaw, roll = _rotation_matrix_to_euler_degrees(rotation_matrix, np)
        return pitch, yaw, roll
    except Exception as error:  # noqa: BLE001 - a PnP fault leaves head pose unavailable
        logger.warning(
            "openface_head_pose_pnp_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None, None, None


def _rotation_matrix_to_euler_degrees(
    rotation_matrix: Any, np: Any
) -> tuple[float, float, float]:
    """Convert a rotation matrix to ``(pitch, yaw, roll)`` Euler angles in degrees.

    Uses the standard XYZ decomposition with a gimbal-lock guard. Pitch follows
    the +up convention used by the existing head-pitch series so downstream nod
    detection and calibration keep their meaning.
    """
    sy = math.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
    if sy >= 1e-6:
        x = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
        y = math.atan2(-rotation_matrix[2, 0], sy)
        z = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
    else:  # gimbal lock: roll is undefined, fold it into pitch
        x = math.atan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
        y = math.atan2(-rotation_matrix[2, 0], sy)
        z = 0.0
    # x ~ pitch, y ~ yaw, z ~ roll. Negate pitch so nodding "down" and "up"
    # match the +up convention of the prior series (sign cancels in the relative
    # nod amplitude regardless, but this keeps the neutral-pose sign consistent).
    pitch = -math.degrees(x)
    yaw = math.degrees(y)
    roll = math.degrees(z)
    return pitch, yaw, roll


def _au12_activation(au_output: Any) -> float | None:
    """Select the AU12 activation from the multitask AU head output.

    The AU head emits an 8-value vector; :data:`AU12_INDEX` locates AU12
    (lip-corner puller) within it. Accepts a batched ``(1, 8)`` or flat ``(8,)``
    shape. Returns ``None`` when the value is missing or non-finite rather than
    fabricating one.
    """
    values = _as_float_sequence(au_output)
    if values is None:
        return None
    # Unwrap a single-row batch, e.g. a ``(1, 8)`` tensor iterates into one row.
    if len(values) == 1:
        inner = _as_float_sequence(au_output[0])
        if inner is not None:
            values = inner
    if AU12_INDEX >= len(values):
        return None
    return values[AU12_INDEX]


def _raw_features_for_turn(
    rows: list[dict[str, Any]],
    turn: StudentTurnVideo,
) -> NonverbalRawFeatures:
    """Assemble raw per-frame series and frame-level quality for one turn.

    Equivalent to the previous extractor's ``_raw_features_for_turn``. No
    thresholds are applied and no metric is derived. Frames whose face was not
    detected (``face_score is None``) are excluded from the per-signal series but
    still counted in ``sampled_frame_count`` for quality. Missing per-signal
    values are dropped from their series so that absent evidence is represented as
    a shorter series, never as a fabricated number (Req 4.1, 4.2, 4.7).

    ``face_not_detected`` is recorded for all-undetected windows and
    ``no_sampled_frames_in_turn`` for empty windows (Req 4.3, 4.4).

    Field-population failure (Req 2.9): assembling the per-signal series and the
    :class:`NonverbalRawFeatures` payload can, in principle, fail after the
    frames were already mapped (for example a serialization error, a
    ``MemoryError`` while building large series, or an ``OSError``). When that
    happens the turn does not crash and no value is fabricated: the affected
    fields fall back to **empty sample series**, a ``field_population_failed``
    quality issue is recorded, the failure is logged, and the turn completes so
    the rest of the interview extraction proceeds. Availability is preserved and
    the loss of evidence stays observable (visible in ``video_quality.issues``),
    never silent.
    """
    ordered = sorted(rows, key=lambda row: row["timestamp_ms"])
    valid_rows = [row for row in ordered if row["face_score"] is not None]

    issues: list[str] = []
    if not ordered:
        issues.append("no_sampled_frames_in_turn")
    if not valid_rows:
        issues.append("face_not_detected")

    extractor = {
        "name": EXTRACTOR_NAME,
        "version": EXTRACTOR_VERSION,
        "detector": DETECTOR_NAME,
        "sample_fps": SAMPLE_FPS,
        "batch_size": BATCH_SIZE,
        "device": DEVICE,
        "face_detection_threshold": FACE_DETECTION_THRESHOLD,
    }

    def _series(key: str) -> list[float]:
        return [row[key] for row in valid_rows if row[key] is not None]

    try:
        return NonverbalRawFeatures(
            face_score_samples=[row["face_score"] for row in valid_rows],
            gaze_yaw_samples=_series("gaze_yaw"),
            gaze_pitch_samples=_series("gaze_pitch"),
            au12_samples=_series("au12"),
            head_pitch_samples=_series("head_pitch"),
            head_yaw_samples=_series("head_yaw"),
            head_roll_samples=_series("head_roll"),
            frame_timestamps_ms=[float(row["timestamp_ms"]) for row in valid_rows],
            sample_fps=SAMPLE_FPS,
            turn_duration_ms=max(turn.end_ms - turn.start_ms, 0),
            extractor=extractor,
            video_quality={
                "sampled_frame_count": len(ordered),
                "valid_frame_count": len(valid_rows),
                "issues": issues,
            },
        )
    except (MemoryError, OSError, ValueError, TypeError) as error:
        # Post-mapping population failure: degrade the affected evidence to
        # unavailable rather than aborting the turn or fabricating a value
        # (Req 2.9). Empty series are emitted, the fault is recorded as a quality
        # issue, and the frame-level counts are still reported so the loss stays
        # observable.
        logger.warning(
            "openface_field_population_failed turn_id=%s error=%s",
            turn.turn_id,
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        if "field_population_failed" not in issues:
            issues.append("field_population_failed")
        return NonverbalRawFeatures(
            face_score_samples=[],
            gaze_yaw_samples=[],
            gaze_pitch_samples=[],
            au12_samples=[],
            head_pitch_samples=[],
            head_yaw_samples=[],
            head_roll_samples=[],
            frame_timestamps_ms=[],
            sample_fps=SAMPLE_FPS,
            turn_duration_ms=max(turn.end_ms - turn.start_ms, 0),
            extractor=extractor,
            video_quality={
                "sampled_frame_count": len(ordered),
                "valid_frame_count": len(valid_rows),
                "issues": issues,
            },
        )
