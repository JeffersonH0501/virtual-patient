"""Centralized personal-baseline calibration helper (Requirement 15).

This module is the single home for deriving and reading the per-participant
:class:`~app.multimodal.schemas.PersonalBaseline` (Requirement 15.8). It does two
things and nothing else:

1. :func:`derive_personal_baseline` computes numeric-only baseline metrics from
   already-provided temporary calibration media (audio and/or video), reusing the
   existing extractors. It never persists media and never fabricates a value:
   anything that cannot be derived causes the whole baseline to be reported as
   unavailable rather than being invented.
2. :func:`read_personal_baseline` is THE single accessor the pipeline uses to read
   the stored baseline from ``interview_metadata.calibration.personal_baseline``,
   validating it against the :class:`PersonalBaseline` schema. No other code path
   should reach into that nested dict directly.

Design constraints preserved here:

* Fundamental frequency is expressed in semitones only, never in Hertz
  (Requirement 15.6, 7.6). The OpenSMILE extractor already emits voiced F0 in
  semitones, so the baseline median is a median of those semitone samples.
* The baseline is numeric-only and behavioural/contextual; it is not a measure of
  empathy, attention, warmth, or any psychological state.
* No new database table is introduced (Requirement 15.8); the baseline lives in
  the existing ``interview_metadata`` JSON.
* This helper works on temp paths and returns metrics only. It does not write the
  baseline, run the endpoint, delete media, or wire any router. Persisting the
  baseline, deleting the temporary media, and exposing the endpoint are the
  responsibility of task 5.2.

Baseline derivation methods
---------------------------
* ``baseline_f0_semitones``: median of the voiced F0 samples (in semitones) over
  the whole calibration audio, obtained by running the OpenSMILE extractor over a
  single window that spans the entire calibration recording.
* ``baseline_loudness``: median of the loudness samples over the same audio.
* ``neutral_head_yaw`` / ``neutral_head_pitch`` / ``neutral_head_roll``: median of
  the shared MediaPipe head-pose series (Yaw/Pitch/Roll) over the whole video.
  Pitch was already emitted by the extractor; yaw and roll were added there as
  raw series specifically for this calibration use.
* ``neutral_gaze_yaw`` / ``neutral_gaze_pitch``: median gaze on both axes. Both
  are required; missing gaze makes the baseline unavailable.

Unavailable paths
-----------------
* If the calibration audio is missing, disabled, or yields no voiced F0 /
  loudness samples, the required audio metrics cannot be derived and the whole
  baseline is reported as ``None`` (unavailable), never fabricated.
* If the calibration video is missing, disabled, or yields no head-pose samples
  on all three axes, the required head metrics cannot be derived and the whole
  baseline is reported as ``None``.
* If either gaze axis has no samples, the whole baseline is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any, Protocol

from app.multimodal.schemas import PersonalBaseline


# A window large enough to span any realistic calibration recording. The
# extractors operate on turn windows; calibration has no turns, so a single
# window from 0 to this bound captures the entire media (FFmpeg decodes to EOF
# and visual observations use absolute media timestamps).
_FULL_MEDIA_WINDOW_END_MS = 24 * 60 * 60 * 1000  # 24 hours

# Placeholder transcript for the single calibration audio window. It only feeds
# the extractor's word-count/quality path and is not used by baseline derivation.
_CALIBRATION_WINDOW_TURN_ID = "calibration"


class _MetadataCarrier(Protocol):
    """Minimal interface for the read helper: anything exposing metadata.

    Both the ORM ``MedicalInterviewDB`` and the pydantic ``MedicalInterview``
    expose ``interview_metadata``; the helper only needs that attribute.
    """

    interview_metadata: dict[str, Any] | None


def derive_personal_baseline(
    *,
    audio_path: Path | None = None,
    video_path: Path | None = None,
    min_voiced_duration_ms: int | None = None,
) -> PersonalBaseline | None:
    """Derive a numeric-only :class:`PersonalBaseline` from calibration media.

    Both media are optional, but the required baseline metrics depend on both:
    the F0/loudness baseline needs calibration audio and the neutral head pose
    needs calibration video. If either group of required metrics cannot be
    derived, the whole baseline is unavailable and ``None`` is returned rather
    than fabricating any value.

    ``audio_path`` and ``video_path`` are temporary files provided by the caller;
    this function does not persist or delete them. ``min_voiced_duration_ms`` is a
    passed-in methodology input forwarded to the audio extractor for its quality
    flag only; when omitted the extractor's own default is used.

    Returns the derived :class:`PersonalBaseline`, or ``None`` when the required
    metrics are unavailable.
    """
    audio_metrics = _derive_audio_metrics(
        audio_path, min_voiced_duration_ms=min_voiced_duration_ms
    )
    head_metrics, gaze_metrics = _derive_video_metrics(video_path)

    if audio_metrics is None or head_metrics is None or gaze_metrics is None:
        # A required metric group could not be derived; do not fabricate.
        return None

    baseline_f0_semitones, baseline_loudness = audio_metrics
    neutral_head_yaw, neutral_head_pitch, neutral_head_roll = head_metrics
    neutral_gaze_yaw, neutral_gaze_pitch = gaze_metrics

    return PersonalBaseline(
        baseline_f0_semitones=baseline_f0_semitones,
        baseline_loudness=baseline_loudness,
        neutral_head_yaw=neutral_head_yaw,
        neutral_head_pitch=neutral_head_pitch,
        neutral_head_roll=neutral_head_roll,
        neutral_gaze_yaw=neutral_gaze_yaw,
        neutral_gaze_pitch=neutral_gaze_pitch,
    )


def read_personal_baseline(interview: _MetadataCarrier | None) -> PersonalBaseline | None:
    """Read and validate the stored baseline; the single pipeline accessor.

    Parses ``interview_metadata.calibration.personal_baseline`` and validates it
    against the :class:`PersonalBaseline` schema. Returns ``None`` when no
    baseline is stored or the stored payload does not satisfy the schema, so the
    pipeline can treat a missing/invalid baseline as ``missing_calibration``
    without scattering nested-dict access across the codebase.
    """
    if interview is None:
        return None
    metadata = getattr(interview, "interview_metadata", None) or {}
    calibration = metadata.get("calibration")
    if not isinstance(calibration, dict):
        return None
    stored = calibration.get("personal_baseline")
    if not isinstance(stored, dict):
        return None
    try:
        return PersonalBaseline.model_validate(stored)
    except Exception:
        # A stored payload that does not satisfy the schema is treated as no
        # baseline rather than raising, so the pipeline degrades gracefully.
        return None


def read_calibration_profile(interview: _MetadataCarrier | None) -> dict[str, Any] | None:
    """Read the stored calibration ``profile`` dict from the interview metadata.

    The profile holds the gaze affine matrix and other visual references the
    multimodal pipeline needs to reconstruct the participant-specific gaze
    tracker. It lives alongside the personal baseline under
    ``interview_metadata.calibration``. Returns ``None`` when no profile is
    stored so the pipeline can fall back to an uncalibrated tracker.
    """
    if interview is None:
        return None
    metadata = getattr(interview, "interview_metadata", None) or {}
    calibration = metadata.get("calibration")
    if not isinstance(calibration, dict):
        return None
    profile = calibration.get("profile")
    return profile if isinstance(profile, dict) else None


def read_calibration(interview: _MetadataCarrier | None) -> dict[str, Any] | None:
    """Read the stored calibration block from ``interview_metadata.calibration``.

    This is the single accessor for the whole persisted calibration record (its
    ``status``, ``profile``, ``personal_baseline`` and remaining metadata), so
    callers that need the block itself do not scatter nested-dict access across
    the codebase. Returns ``None`` when no calibration block is stored.
    """
    if interview is None:
        return None
    metadata = getattr(interview, "interview_metadata", None) or {}
    calibration = metadata.get("calibration")
    return calibration if isinstance(calibration, dict) else None


def calibration_passed(interview: _MetadataCarrier | None) -> bool:
    """Report whether the interview carries a passed calibration usable to start.

    A calibration is usable when its persisted block is marked ``passed`` and a
    valid :class:`PersonalBaseline` can be read back. This mirrors the guarantee
    made at save time (a passed calibration always carries a valid baseline) and
    centralizes the interview-start gate so it does not reach into the metadata
    dict directly.
    """
    calibration = read_calibration(interview)
    if not calibration or calibration.get("status") != "passed":
        return False
    return read_personal_baseline(interview) is not None


def _derive_audio_metrics(
    audio_path: Path | None,
    *,
    min_voiced_duration_ms: int | None,
) -> tuple[float, float] | None:
    """Return ``(baseline_f0_semitones, baseline_loudness)`` or ``None``.

    Runs the OpenSMILE extractor over a single window spanning the whole
    calibration audio and takes the median of the voiced F0 samples (in
    semitones) and the median of the loudness samples.
    """
    if audio_path is None:
        return None

    from app.paraverbal.opensmile_extractor import (
        StudentTurnAudio,
        analyze_student_turns,
    )

    window = StudentTurnAudio(
        turn_id=_CALIBRATION_WINDOW_TURN_ID,
        start_ms=0,
        end_ms=_FULL_MEDIA_WINDOW_END_MS,
        transcript=_CALIBRATION_WINDOW_TURN_ID,
    )
    kwargs: dict[str, Any] = {}
    if min_voiced_duration_ms is not None:
        kwargs["min_voiced_duration_ms"] = min_voiced_duration_ms
    extracted = analyze_student_turns(audio_path, [window], **kwargs)
    raw = extracted.get(_CALIBRATION_WINDOW_TURN_ID)
    if raw is None:
        return None

    f0_samples = raw.f0_samples_semitones
    loudness_samples = raw.loudness_samples
    if not f0_samples or not loudness_samples:
        return None
    return float(median(f0_samples)), float(median(loudness_samples))


def _derive_video_metrics(
    video_path: Path | None,
) -> tuple[tuple[float, float, float] | None, tuple[float, float] | None]:
    """Return ``(head_metrics, gaze_metrics)`` from the calibration video.

    ``head_metrics`` is ``(neutral_head_yaw, neutral_head_pitch,
    neutral_head_roll)`` when all three head-pose axes have samples, otherwise
    ``None`` (the required head baseline is then unavailable). ``gaze_metrics`` is
    ``(neutral_gaze_yaw, neutral_gaze_pitch)`` where each element is the median
    gaze when both axes are available; otherwise the gaze group is ``None``.
    """
    if video_path is None:
        return None, None

    from app.nonverbal.ccdbhg import head_pose_features
    from app.nonverbal.video_observations import extract_nonverbal_video_observations

    observations = extract_nonverbal_video_observations(video_path)
    head_samples = [
        head_pose_features(item.shared.facial_transformation_matrix)
        for item in observations
        if item.shared.face_valid and item.shared.facial_transformation_matrix is not None
    ]
    gaze_samples = [
        (item.gaze.unclipped_x, item.gaze.unclipped_y)
        for item in observations
        if item.gaze.valid and item.gaze.unclipped_x is not None and item.gaze.unclipped_y is not None
    ]
    if not head_samples and not gaze_samples:
        return None, None
    if head_samples:
        head_yaw_samples, head_roll_samples, head_pitch_samples = zip(*head_samples)
        head_metrics: tuple[float, float, float] | None = (
            float(median(head_yaw_samples)),
            float(median(head_pitch_samples)),
            float(median(head_roll_samples)),
        )
    else:
        head_metrics = None

    gaze_x_samples, gaze_y_samples = zip(*gaze_samples) if gaze_samples else ((), ())
    gaze_metrics = (float(median(gaze_x_samples)), float(median(gaze_y_samples))) if gaze_samples else None
    return head_metrics, gaze_metrics
