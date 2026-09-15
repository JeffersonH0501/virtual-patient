"""Multimodal pipeline orchestration (Requirements 17, 18, 19, 24, 25).

This module owns the *scientific orchestration* of the staged, versioned
multimodal pipeline. It is intentionally the only place that wires the stages
together; the router merely schedules :func:`process_multimodal_interview` as a
background task (task 6.2). Moving orchestration here keeps the router thin and
keeps the methodology in one auditable place.

The 16-step flow (design section "pipeline.py — orchestration"):

1.  Open a DB session, load the recording + interview; return early if missing.
2.  Load the methodology config once (capturing ``versions`` + ``config_hash``
    for every result).
3.  Read the personal baseline (``calibration.read_personal_baseline``).
4.  Resolve turn windows: student turns feed paraverbal; all turns feed
    nonverbal. The interaction context is ``speaking`` for student turns and
    ``listening`` for patient turns.
5.  Update ``observation_processing`` (stage + status) on every transition.
6.  Run OpenSMILE once over the needed student segments.
7.  Preprocess paraverbal per student turn.
8.  Run Py-Feat once over the full video, segmented by turn window.
9.  Preprocess nonverbal per turn.
10. Compute ``SessionReferences`` once with the two-pass ``min_turns`` guard.
11. Run the threshold engine per turn.
12. Run the label engine per turn.
13. Assemble one :class:`MultimodalTurnResult` per turn and persist the layered
    JSON into ``interview_turns.paraverbal`` / ``.nonverbal_features``.
14. Batch the DB writes into a single commit near the end.
15. Set the final ``observation_processing`` status
    (``complete`` / ``partial`` / ``failed`` / ``unavailable``) from the
    error/quality taxonomy: a single missing feature/modality yields
    ``partial``, never ``failed``.
16. Structured logging at each stage; no ``print()``.

Design boundaries preserved here:

* NO interview-level aggregation and NO late fusion (Requirement 17.4, 20.4).
  After the ``labeling`` stage the pipeline reaches a clear, stubbed hand-off
  point (:func:`_late_fusion_handoff`) and stops; the downstream
  recording -> multimodal -> text-evaluation -> late-fusion -> feedback-coherence
  sequence is only *prepared*, not implemented.
* Paraverbal features are never fabricated for patient turns (Requirement 17.3):
  the paraverbal layer is ``None`` for patient turns. The nonverbal layer is
  present for all turns (Requirement 17.2).
* Every unavailable value is represented with ``null`` + ``status`` + ``reason``
  and never a fabricated number (Requirement 16.3, 24.3).
* Performance: Py-Feat is opened once over the full video; OpenSMILE runs once
  per needed student segment; session percentiles are computed once; the DB
  writes are batched into a single commit (Requirement 19.2-19.5).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.core.config import settings
from app.core.database import SessionLocal
from app.media import get_media_storage
from app.models.medical_interview import (
    InterviewMediaAssetDB,
    InterviewRecordingDB,
    InterviewTurnDB,
    MediaAssetKind,
    MedicalInterviewDB,
)
from app.multimodal.calibration import read_personal_baseline
from app.multimodal.config_loader import (
    ConfigError,
    MethodologyConfig,
    load_methodology_config,
)
from app.multimodal.label_engine import (
    integrate_nonverbal_labels,
    integrate_paraverbal_labels,
)
from app.multimodal.schemas import (
    ModalityLayer,
    MultimodalTurnResult,
    NonverbalProcessedFeatures,
    NonverbalRawFeatures,
    OutcomeStatus,
    ParaverbalProcessedFeatures,
    ParaverbalRawFeatures,
    PersonalBaseline,
    UnavailableReason,
)
from app.multimodal.threshold_engine import (
    compute_nonverbal_base_labels,
    compute_paraverbal_base_labels,
)
from app.nonverbal.preprocessing import (
    NodDetectionParams,
    preprocess_nonverbal_turn,
)
from app.nonverbal.pyfeat_extractor import (
    StudentTurnVideo,
    analyze_pyfeat_student_turn_videos,
)
from app.paraverbal.opensmile_extractor import (
    StudentTurnAudio,
    analyze_student_turns,
)
from app.paraverbal.preprocessing import preprocess_paraverbal


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# observation_processing lifecycle vocabulary (Requirement 18)
# ---------------------------------------------------------------------------

# Stages, in the order the pipeline traverses them.
STAGE_QUEUED = "queued"
STAGE_CALIBRATION = "calibration"
STAGE_PARAVERBAL_EXTRACTION = "paraverbal_extraction"
STAGE_PARAVERBAL_PREPROCESSING = "paraverbal_preprocessing"
STAGE_NONVERBAL_EXTRACTION = "nonverbal_extraction"
STAGE_NONVERBAL_PREPROCESSING = "nonverbal_preprocessing"
STAGE_THRESHOLDING = "thresholding"
STAGE_LABELING = "labeling"
STAGE_FINISHED = "finished"

# Statuses.
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"

# Session-relative features whose per-session P25/P75 references drive the
# session_percentiles strategy (thresholds.yaml). Kept here as the single list
# the two-pass step iterates so the reference computation stays in lock-step
# with the config without re-parsing YAML per feature.
_PARAVERBAL_SESSION_FEATURES = ("median_loudness", "loudness_p20_p80_range")
_NONVERBAL_SESSION_FEATURES = ("nod_rate_min", "mean_smile_activation")

# Percentile keys the session_percentiles strategy reads by default.
_SESSION_PERCENTILES = {"p25": 0.25, "p75": 0.75}

_STUDENT_SPEAKER = "student"
_CONTEXT_SPEAKING = "speaking"
_CONTEXT_LISTENING = "listening"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def process_multimodal_interview(
    interview_id: int,
    recording_id: str,
) -> None:
    """Run the full multimodal pipeline for one finalized recording.

    Scheduled by the router as a background task
    (``background_tasks.add_task(process_multimodal_interview, ...)``). It owns
    its own DB session (like the legacy router processing function) and never
    raises to its caller: any unexpected failure is logged and recorded as a
    ``failed`` observation-processing status so the interview is not left in an
    ambiguous state.
    """
    db = SessionLocal()
    try:
        recording = (
            db.query(InterviewRecordingDB)
            .filter(
                InterviewRecordingDB.id == recording_id,
                InterviewRecordingDB.medical_interview_id == interview_id,
            )
            .first()
        )
        if recording is None:
            logger.warning(
                "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
                "result=skipped reason=recording_unavailable",
                interview_id,
                recording_id,
                STAGE_QUEUED,
            )
            return

        interview = (
            db.query(MedicalInterviewDB)
            .filter(MedicalInterviewDB.id == interview_id)
            .first()
        )
        if interview is None:
            logger.warning(
                "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
                "result=skipped reason=interview_unavailable",
                interview_id,
                recording_id,
                STAGE_QUEUED,
            )
            return

        _set_stage(db, recording, STATUS_QUEUED, STAGE_QUEUED)
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "result=started",
            interview_id,
            recording_id,
            STAGE_QUEUED,
        )

        _run_pipeline(
            db=db,
            interview=interview,
            recording=recording,
            interview_id=interview_id,
            recording_id=recording_id,
        )
    except ConfigError as error:
        # A misconfiguration is a whole-pipeline failure: no result can be
        # trusted, so mark the run failed and name the failing file in the log.
        db.rollback()
        _mark_failed(db, recording_id)
        logger.exception(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "result=failed reason=config_error detail=%s",
            interview_id,
            recording_id,
            STAGE_FINISHED,
            error,
        )
    except Exception:  # noqa: BLE001 - background task must not propagate.
        db.rollback()
        _mark_failed(db, recording_id)
        logger.exception(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "result=failed reason=processing_error",
            interview_id,
            recording_id,
            STAGE_FINISHED,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Orchestration core
# ---------------------------------------------------------------------------


def _run_pipeline(
    *,
    db: Any,
    interview: MedicalInterviewDB,
    recording: InterviewRecordingDB,
    interview_id: int,
    recording_id: str,
) -> None:
    """Execute steps 2-16 of the flow with a single batched commit at the end."""

    # Step 2: load + validate config once; captured on every turn result.
    config = load_methodology_config()
    versions = config.versions.model_dump()
    config_hash = config.config_hash
    para_processing = config.processing.get("paraverbal", {}) or {}
    nonverbal_processing = config.processing.get("nonverbal", {}) or {}
    min_turns_for_session_stats = int(
        config.thresholds.get("min_turns_for_session_stats", 0) or 0
    )

    # Step 3: read the personal baseline (may be None -> missing_calibration).
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_CALIBRATION)
    baseline = read_personal_baseline(interview)
    baseline_available = baseline is not None
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=%s",
        interview_id,
        recording_id,
        STAGE_CALIBRATION,
        "baseline_available" if baseline_available else "missing_calibration",
    )

    # Step 4: resolve turn windows. All turns, ordered by sequence; student
    # turns are the paraverbal subset.
    turns: list[InterviewTurnDB] = (
        db.query(InterviewTurnDB)
        .filter(InterviewTurnDB.medical_interview_id == interview_id)
        .order_by(InterviewTurnDB.sequence)
        .all()
    )
    student_turns = [turn for turn in turns if turn.speaker == _STUDENT_SPEAKER]

    # Track whether any modality yielded a usable outcome and whether any gap
    # occurred, to decide complete vs partial vs unavailable at the end.
    outcome = _OutcomeTracker()

    # Step 6: paraverbal extraction (OpenSMILE once per needed student segment).
    paraverbal_raw = _extract_paraverbal(
        db=db,
        recording=recording,
        interview_id=interview_id,
        recording_id=recording_id,
        student_turns=student_turns,
        outcome=outcome,
    )

    # Step 7: paraverbal preprocessing per student turn.
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_PARAVERBAL_PREPROCESSING)
    min_pause_ms = para_processing.get("min_pause_ms")
    paraverbal_processed: dict[str, ParaverbalProcessedFeatures] = {}
    for turn in student_turns:
        raw = paraverbal_raw.get(turn.id)
        if raw is None:
            continue
        paraverbal_processed[turn.id] = preprocess_paraverbal(
            raw, min_pause_ms=min_pause_ms, baseline=baseline
        )

    # Step 8: nonverbal extraction (Py-Feat once over the full video).
    nonverbal_raw, nonverbal_context = _extract_nonverbal(
        db=db,
        recording=recording,
        interview_id=interview_id,
        recording_id=recording_id,
        turns=turns,
        outcome=outcome,
    )

    # Step 9: nonverbal preprocessing per turn.
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_NONVERBAL_PREPROCESSING)
    nod_params = _nod_params(nonverbal_processing)
    alignment_tolerance = _gaze_tolerance(nonverbal_processing)
    au12_threshold = _au12_threshold(nonverbal_processing)
    nonverbal_processed: dict[str, NonverbalProcessedFeatures] = {}
    nonverbal_reasons: dict[str, dict[str, UnavailableReason]] = {}
    for turn in turns:
        raw = nonverbal_raw.get(turn.id)
        if raw is None:
            continue
        result = preprocess_nonverbal_turn(
            raw,
            nonverbal_context.get(turn.id, _context_for(turn)),
            baseline=baseline,
            alignment_tolerance_radians=alignment_tolerance,
            au12_active_threshold=au12_threshold,
            nod_params=nod_params,
        )
        nonverbal_processed[turn.id] = result.processed
        nonverbal_reasons[turn.id] = result.reasons

    # Step 10: compute SessionReferences once (two-pass, guarded).
    para_session_refs = _session_references(
        processed_by_turn=paraverbal_processed,
        feature_names=_PARAVERBAL_SESSION_FEATURES,
        min_turns=min_turns_for_session_stats,
    )
    nonverbal_session_refs = _session_references(
        processed_by_turn=nonverbal_processed,
        feature_names=_NONVERBAL_SESSION_FEATURES,
        min_turns=min_turns_for_session_stats,
    )
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=session_refs paraverbal_available=%s nonverbal_available=%s "
        "min_turns=%s",
        interview_id,
        recording_id,
        STAGE_THRESHOLDING,
        para_session_refs is not None,
        nonverbal_session_refs is not None,
        min_turns_for_session_stats,
    )

    # Steps 11-13: threshold + label + assemble per turn.
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_THRESHOLDING)
    results: list[tuple[InterviewTurnDB, MultimodalTurnResult]] = []
    for turn in turns:
        result = _assemble_turn_result(
            turn=turn,
            config=config,
            versions=versions,
            config_hash=config_hash,
            baseline_available=baseline_available,
            paraverbal_raw=paraverbal_raw.get(turn.id),
            paraverbal_processed=paraverbal_processed.get(turn.id),
            para_session_refs=para_session_refs,
            nonverbal_raw=nonverbal_raw.get(turn.id),
            nonverbal_processed=nonverbal_processed.get(turn.id),
            nonverbal_reasons=nonverbal_reasons.get(turn.id, {}),
            nonverbal_session_refs=nonverbal_session_refs,
            outcome=outcome,
        )
        results.append((turn, result))

    _set_stage(db, recording, STATUS_PROCESSING, STAGE_LABELING)

    # Hand-off point: interview-level aggregation and late fusion are NOT done
    # here (Requirement 17.4, 20.4). This is only a prepared boundary.
    _late_fusion_handoff(interview_id=interview_id, recording_id=recording_id)

    # Steps 13-14: batch-persist all per-turn layered results in one commit.
    for turn, result in results:
        _persist_turn(turn, result)
    db.commit()
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=persisted turn_count=%s",
        interview_id,
        recording_id,
        STAGE_LABELING,
        len(results),
    )

    # Step 15: final status from the outcome/quality taxonomy.
    final_status = outcome.final_status()
    _set_stage(
        db,
        recording,
        final_status,
        STAGE_FINISHED,
        turn_count=len(results),
        student_turn_count=len(student_turns),
    )
    db.commit()
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=%s",
        interview_id,
        recording_id,
        STAGE_FINISHED,
        final_status,
    )


# ---------------------------------------------------------------------------
# Extraction stages
# ---------------------------------------------------------------------------


def _extract_paraverbal(
    *,
    db: Any,
    recording: InterviewRecordingDB,
    interview_id: int,
    recording_id: str,
    student_turns: Sequence[InterviewTurnDB],
    outcome: "_OutcomeTracker",
) -> dict[str, ParaverbalRawFeatures]:
    """Run OpenSMILE once over the needed student segments (Requirement 19.2).

    Guarded by ``settings.paraverbal_analysis_enabled``. Returns a mapping of
    ``turn_id -> ParaverbalRawFeatures`` for turns that yielded a usable signal;
    turns absent from the mapping are treated downstream as unavailable. An
    extractor exception marks the paraverbal modality as an extractor failure
    without failing the whole run (Requirement 24.2).
    """
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_PARAVERBAL_EXTRACTION)
    if not settings.paraverbal_analysis_enabled or not student_turns:
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=paraverbal result=skipped reason=%s",
            interview_id,
            recording_id,
            STAGE_PARAVERBAL_EXTRACTION,
            "disabled" if not settings.paraverbal_analysis_enabled else "no_student_turns",
        )
        return {}

    storage = get_media_storage()
    asset = _ready_asset(db, recording.id, MediaAssetKind.STUDENT_AUDIO.value)
    if asset is None:
        outcome.note_gap()
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=paraverbal result=unavailable reason=student_audio_unavailable",
            interview_id,
            recording_id,
            STAGE_PARAVERBAL_EXTRACTION,
        )
        return {}

    try:
        audio_path = storage.resolve(asset.storage_key)
        windows = [
            StudentTurnAudio(
                turn_id=turn.id,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                transcript=turn.transcript,
            )
            for turn in student_turns
        ]
        extracted = analyze_student_turns(audio_path, windows)
    except Exception:  # noqa: BLE001 - one modality failing must not fail all.
        outcome.note_gap()
        logger.exception(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=paraverbal result=extractor_failure",
            interview_id,
            recording_id,
            STAGE_PARAVERBAL_EXTRACTION,
        )
        return {}

    if len(extracted) < len(student_turns):
        # Some segments had insufficient signal; the run is partial, not failed.
        outcome.note_gap()
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "modality=paraverbal result=extracted student_turn_count=%s observed=%s",
        interview_id,
        recording_id,
        STAGE_PARAVERBAL_EXTRACTION,
        len(student_turns),
        len(extracted),
    )
    return extracted


def _extract_nonverbal(
    *,
    db: Any,
    recording: InterviewRecordingDB,
    interview_id: int,
    recording_id: str,
    turns: Sequence[InterviewTurnDB],
    outcome: "_OutcomeTracker",
) -> tuple[dict[str, NonverbalRawFeatures], dict[str, str]]:
    """Run Py-Feat once over the full video, segmented by turn (Requirement 19.3).

    ``analyze_pyfeat_student_turn_videos`` opens the detector once over the whole
    video and segments the rows by each turn window, so this is a single call for
    all turns. It returns ``turn_id -> {NonverbalRawFeatures.model_dump() +
    observationContext}``; we reconstruct :class:`NonverbalRawFeatures` by
    validating the raw portion (dropping ``observationContext``) and read the
    conversation speaker from ``observationContext`` to derive the context.
    """
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_NONVERBAL_EXTRACTION)
    if not settings.pyfeat_analysis_enabled or not turns:
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=nonverbal result=skipped reason=%s",
            interview_id,
            recording_id,
            STAGE_NONVERBAL_EXTRACTION,
            "disabled" if not settings.pyfeat_analysis_enabled else "no_turns",
        )
        return {}, {}

    storage = get_media_storage()
    asset = _ready_asset(db, recording.id, MediaAssetKind.STUDENT_VIDEO.value)
    if asset is None:
        outcome.note_gap()
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=nonverbal result=unavailable reason=student_video_unavailable",
            interview_id,
            recording_id,
            STAGE_NONVERBAL_EXTRACTION,
        )
        return {}, {}

    try:
        video_path = storage.resolve(asset.storage_key)
        windows = [
            StudentTurnVideo(
                turn_id=turn.id,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                conversation_speaker=turn.speaker,
            )
            for turn in turns
        ]
        extracted = analyze_pyfeat_student_turn_videos(video_path, windows)
    except Exception:  # noqa: BLE001 - one modality failing must not fail all.
        outcome.note_gap()
        logger.exception(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=nonverbal result=extractor_failure",
            interview_id,
            recording_id,
            STAGE_NONVERBAL_EXTRACTION,
        )
        return {}, {}

    raw_by_turn: dict[str, NonverbalRawFeatures] = {}
    context_by_turn: dict[str, str] = {}
    for turn_id, payload in extracted.items():
        raw_dict = {key: value for key, value in payload.items() if key != "observationContext"}
        try:
            raw_by_turn[turn_id] = NonverbalRawFeatures.model_validate(raw_dict)
        except Exception:  # noqa: BLE001 - a malformed row is a per-turn gap.
            outcome.note_gap()
            logger.warning(
                "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
                "modality=nonverbal turn_id=%s result=processing_error "
                "reason=raw_validation_failed",
                interview_id,
                recording_id,
                STAGE_NONVERBAL_EXTRACTION,
                turn_id,
            )
            continue
        context = (payload.get("observationContext") or {}).get("conversationSpeaker")
        if context is not None:
            context_by_turn[turn_id] = _context_for_speaker(context)

    if len(raw_by_turn) < len(turns):
        outcome.note_gap()
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "modality=nonverbal result=extracted turn_count=%s observed=%s",
        interview_id,
        recording_id,
        STAGE_NONVERBAL_EXTRACTION,
        len(turns),
        len(raw_by_turn),
    )
    return raw_by_turn, context_by_turn


# ---------------------------------------------------------------------------
# Per-turn assembly (threshold + label + layered result)
# ---------------------------------------------------------------------------


def _assemble_turn_result(
    *,
    turn: InterviewTurnDB,
    config: MethodologyConfig,
    versions: dict,
    config_hash: str,
    baseline_available: bool,
    paraverbal_raw: ParaverbalRawFeatures | None,
    paraverbal_processed: ParaverbalProcessedFeatures | None,
    para_session_refs: dict[str, dict[str, float]] | None,
    nonverbal_raw: NonverbalRawFeatures | None,
    nonverbal_processed: NonverbalProcessedFeatures | None,
    nonverbal_reasons: dict[str, UnavailableReason],
    nonverbal_session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> MultimodalTurnResult:
    """Run the threshold + label engines and build one turn's layered result.

    Paraverbal is only computed for student turns; for patient turns the
    paraverbal layer is ``None`` and is never fabricated (Requirement 17.3). The
    nonverbal layer is always attempted (Requirement 17.2).
    """
    context = _context_for(turn)
    is_student = turn.speaker == _STUDENT_SPEAKER

    paraverbal_layer: ModalityLayer | None = None
    if is_student:
        paraverbal_layer = _paraverbal_layer(
            config=config,
            baseline_available=baseline_available,
            raw=paraverbal_raw,
            processed=paraverbal_processed,
            session_refs=para_session_refs,
            outcome=outcome,
        )

    nonverbal_layer = _nonverbal_layer(
        config=config,
        baseline_available=baseline_available,
        raw=nonverbal_raw,
        processed=nonverbal_processed,
        reasons=nonverbal_reasons,
        session_refs=nonverbal_session_refs,
        outcome=outcome,
    )

    return MultimodalTurnResult(
        turn_id=turn.id,
        modality_context=context,
        paraverbal=paraverbal_layer,
        nonverbal=nonverbal_layer,
        versions=versions,
        config_hash=config_hash,
    )


def _paraverbal_layer(
    *,
    config: MethodologyConfig,
    baseline_available: bool,
    raw: ParaverbalRawFeatures | None,
    processed: ParaverbalProcessedFeatures | None,
    session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> ModalityLayer:
    """Build the paraverbal :class:`ModalityLayer` for one student turn."""
    if raw is None or processed is None:
        outcome.note_gap()
        return ModalityLayer(
            status=OutcomeStatus.UNAVAILABLE,
            reason=UnavailableReason.INSUFFICIENT_SIGNAL,
        )

    base_labels = compute_paraverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
    )
    integrated = integrate_paraverbal_labels(base_labels, config)
    outcome.note_ok()
    return ModalityLayer(
        raw=raw.model_dump(),
        processed=processed.model_dump(),
        base_labels=base_labels.model_dump(),
        integrated_labels=integrated.model_dump(),
        quality=raw.audio_quality,
        status=OutcomeStatus.OK,
    )


def _nonverbal_layer(
    *,
    config: MethodologyConfig,
    baseline_available: bool,
    raw: NonverbalRawFeatures | None,
    processed: NonverbalProcessedFeatures | None,
    reasons: dict[str, UnavailableReason],
    session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> ModalityLayer:
    """Build the nonverbal :class:`ModalityLayer` for one turn (all speakers)."""
    if raw is None or processed is None:
        outcome.note_gap()
        return ModalityLayer(
            status=OutcomeStatus.UNAVAILABLE,
            reason=UnavailableReason.INSUFFICIENT_SIGNAL,
        )

    base_labels = compute_nonverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
    )
    integrated = integrate_nonverbal_labels(base_labels, config)
    outcome.note_ok()
    quality = dict(raw.video_quality)
    if reasons:
        # Surface per-feature unavailability reasons alongside quality so every
        # null carries an explanation (Requirement 24.3).
        quality = {
            **quality,
            "feature_reasons": {name: reason.value for name, reason in reasons.items()},
        }
    return ModalityLayer(
        raw=raw.model_dump(),
        processed=processed.model_dump(),
        base_labels=base_labels.model_dump(),
        integrated_labels=integrated.model_dump(),
        quality=quality,
        status=OutcomeStatus.OK,
    )


# ---------------------------------------------------------------------------
# Persistence (batched) — layered per-turn JSON, design section 20
# ---------------------------------------------------------------------------


def _persist_turn(turn: InterviewTurnDB, result: MultimodalTurnResult) -> None:
    """Write the layered per-turn result into the existing JSON columns.

    Paraverbal is written only for student turns (``None`` for patient turns, so
    it is never fabricated). Nonverbal is written for all turns. The persisted
    shape matches design section 20: ``raw``/``processed``/``base_labels``/
    ``integrated_labels``/``quality``/``versions``/``config_hash``/``status``/
    ``reason``. This function only stages the columns on the ORM object; the
    caller commits once (batched writes, Requirement 19.5).
    """
    # ``versions`` and ``config_hash`` live on the turn result, not on the
    # per-modality layer; both persisted layers carry the same methodology
    # provenance so each column is independently traceable (Requirement 16.1,
    # 16.2). Reassigning a new dict (never in-place mutation) marks the plain
    # ``Column(JSON)`` attribute dirty, which is exactly how the legacy router
    # persisted ``turn.paraverbal`` before the single commit.
    turn.paraverbal = _layer_to_json(
        result.paraverbal, versions=result.versions, config_hash=result.config_hash
    )
    turn.nonverbal_features = _layer_to_json(
        result.nonverbal, versions=result.versions, config_hash=result.config_hash
    )


def _layer_to_json(
    layer: ModalityLayer | None,
    *,
    versions: dict,
    config_hash: str,
) -> dict[str, Any] | None:
    """Serialize one modality layer to the persisted JSON shape, or ``None``.

    Produces the design section-20 shape: ``raw``/``processed``/``base_labels``/
    ``integrated_labels``/``quality``/``versions``/``config_hash``/``status``/
    ``reason``. ``versions`` and ``config_hash`` are the turn-result provenance
    stamped into every persisted modality layer (Requirement 16.1, 16.2).

    ``None`` (e.g. the paraverbal layer of a patient turn) is stored as SQL
    ``NULL`` rather than an empty object, so patient turns carry no fabricated
    paraverbal payload.
    """
    if layer is None:
        return None
    return {
        "raw": layer.raw,
        "processed": layer.processed,
        "base_labels": layer.base_labels,
        "integrated_labels": layer.integrated_labels,
        "quality": layer.quality,
        "versions": versions,
        "config_hash": config_hash,
        "status": layer.status.value,
        "reason": layer.reason.value if layer.reason is not None else None,
    }


# ---------------------------------------------------------------------------
# Two-pass session references (Requirement 13, 19.4)
# ---------------------------------------------------------------------------


def compute_session_references(
    *,
    processed_by_turn: dict[str, Any],
    feature_names: Sequence[str],
    min_turns: int,
) -> dict[str, dict[str, float]] | None:
    """Public wrapper over :func:`_session_references` for reuse outside the pipeline.

    The relabel script (``scripts/relabel_multimodal.py``) recomputes session
    references from stored processed features using the exact same two-pass,
    guarded percentile logic the pipeline uses, so that relabeling reproduces the
    pipeline's session-relative labels without re-extracting media (Requirement
    21.1, design Property 14). Exposing this thin wrapper keeps that logic in one
    place rather than duplicating the linear-interpolation percentile in the
    script.
    """
    return _session_references(
        processed_by_turn=processed_by_turn,
        feature_names=feature_names,
        min_turns=min_turns,
    )


def _session_references(
    *,
    processed_by_turn: dict[str, Any],
    feature_names: Sequence[str],
    min_turns: int,
) -> dict[str, dict[str, float]] | None:
    """Compute per-feature P25/P75 session references, or ``None`` when guarded.

    Pass 1 (already done by the caller) produced processed features for every
    valid turn. Here, pass 2 computes the session percentiles once: for each
    session-relative feature, gather its non-``None`` values across turns and, if
    at least ``min_turns`` turns qualify, compute P25/P75 with the same linear
    interpolation the preprocessing percentiles use. When fewer than
    ``min_turns`` qualifying turns exist, return ``None`` so every
    session-relative family becomes ``insufficient_reference_data`` (Requirement
    13.3). A feature with no values is simply omitted from the reference map, so
    the threshold engine reports ``insufficient_reference_data`` for it.
    """
    qualifying_turns = len(processed_by_turn)
    if min_turns > 0 and qualifying_turns < min_turns:
        return None
    if qualifying_turns == 0:
        return None

    references: dict[str, dict[str, float]] = {}
    for feature in feature_names:
        values = [
            value
            for processed in processed_by_turn.values()
            if (value := getattr(processed, feature, None)) is not None
        ]
        if len(values) < min_turns or not values:
            continue
        references[feature] = {
            key: _percentile(values, fraction)
            for key, fraction in _SESSION_PERCENTILES.items()
        }
    return references or None


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Percentile via linear interpolation between closest ranks (NumPy default).

    Consistent with ``app/paraverbal/preprocessing._percentile``: for ``n``
    sorted values the target rank is ``fraction * (n - 1)`` and the result
    interpolates linearly between the two bracketing samples. Callers guarantee a
    non-empty input.
    """
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    if count == 1:
        return ordered[0]
    rank = fraction * (count - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, count - 1)
    weight = rank - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


# ---------------------------------------------------------------------------
# Config -> preprocessing parameter adapters
# ---------------------------------------------------------------------------


def _nod_params(nonverbal_processing: dict[str, Any]) -> NodDetectionParams:
    """Build :class:`NodDetectionParams` from the ``nonverbal.nod`` config block.

    Present-``null`` methodology values pass straight through as ``None`` so the
    detector reports ``feature_unavailable`` rather than running with an invented
    threshold (Requirement 4.7).
    """
    nod = nonverbal_processing.get("nod", {}) or {}
    return NodDetectionParams(
        min_amplitude_deg=nod.get("min_amplitude_deg"),
        min_cycle_ms=nod.get("min_cycle_ms"),
        max_cycle_ms=nod.get("max_cycle_ms"),
        smoothing_window_ms=nod.get("smoothing_window_ms"),
    )


def _gaze_tolerance(nonverbal_processing: dict[str, Any]) -> float | None:
    """Read ``nonverbal.gaze.alignment_tolerance_radians`` (may be ``None``)."""
    gaze = nonverbal_processing.get("gaze", {}) or {}
    return gaze.get("alignment_tolerance_radians")


def _au12_threshold(nonverbal_processing: dict[str, Any]) -> float | None:
    """Read ``nonverbal.smile.au12_active_threshold`` (may be ``None``)."""
    smile = nonverbal_processing.get("smile", {}) or {}
    return smile.get("au12_active_threshold")


# ---------------------------------------------------------------------------
# Context helpers (Requirement 9.5)
# ---------------------------------------------------------------------------


def _context_for(turn: InterviewTurnDB) -> str:
    """Interaction context from the turn speaker: student -> speaking else listening."""
    return _context_for_speaker(turn.speaker)


def _context_for_speaker(speaker: str) -> str:
    return _CONTEXT_SPEAKING if speaker == _STUDENT_SPEAKER else _CONTEXT_LISTENING


# ---------------------------------------------------------------------------
# observation_processing lifecycle updates (Requirement 18)
# ---------------------------------------------------------------------------


def _set_stage(
    db: Any,
    recording: InterviewRecordingDB,
    status: str,
    stage: str,
    **details: Any,
) -> None:
    """Write ``observation_processing`` into ``capture_config`` and commit it.

    Reassigns a new dict so SQLAlchemy detects the JSON mutation, then commits so
    the lifecycle is observable in near real time as the pipeline advances. The
    router now only seeds the initial queued marker on finalize and schedules
    this pipeline; the pipeline owns every subsequent lifecycle transition. Kept
    deliberately small: it records status/stage plus optional details only.
    """
    capture_config = dict(recording.capture_config or {})
    capture_config["observation_processing"] = {
        "status": status,
        "stage": stage,
        **details,
    }
    recording.capture_config = capture_config
    db.commit()


def _mark_failed(db: Any, recording_id: str) -> None:
    """Record a terminal ``failed`` observation-processing status after an error.

    Re-fetches the recording on a fresh transaction (the caller has rolled back)
    so the failure is always persisted even when the in-flight object is stale.
    """
    recording = (
        db.query(InterviewRecordingDB)
        .filter(InterviewRecordingDB.id == recording_id)
        .first()
    )
    if recording is None:
        return
    _set_stage(db, recording, STATUS_FAILED, STAGE_FINISHED)


# ---------------------------------------------------------------------------
# Media-asset lookup (reuses the router's pattern)
# ---------------------------------------------------------------------------


def _ready_asset(
    db: Any,
    recording_id: str,
    kind: str,
) -> InterviewMediaAssetDB | None:
    """Return the ready media asset of ``kind`` for a recording, or ``None``.

    Same lookup the router uses: filter by recording, kind, and ``status ==
    'ready'``.
    """
    return (
        db.query(InterviewMediaAssetDB)
        .filter(
            InterviewMediaAssetDB.recording_id == recording_id,
            InterviewMediaAssetDB.kind == kind,
            InterviewMediaAssetDB.status == "ready",
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Outcome taxonomy (Requirement 18, 24.2): complete / partial / unavailable
# ---------------------------------------------------------------------------


class _OutcomeTracker:
    """Tracks whether the run produced usable outcomes and/or hit any gap.

    Final status rules (Requirement 24.2): if at least one modality/family
    yielded a usable outcome and no gap occurred -> ``complete``; if usable
    outcomes exist but any single feature/modality was missing -> ``partial``
    (never ``failed`` for a single gap); if nothing usable was produced ->
    ``unavailable``. A wholesale failure is handled separately by the caller
    (``failed``) via exception handling.
    """

    def __init__(self) -> None:
        self._any_ok = False
        self._any_gap = False

    def note_ok(self) -> None:
        self._any_ok = True

    def note_gap(self) -> None:
        self._any_gap = True

    def final_status(self) -> str:
        if not self._any_ok:
            return STATUS_UNAVAILABLE
        if self._any_gap:
            return STATUS_PARTIAL
        return STATUS_COMPLETE


# ---------------------------------------------------------------------------
# Prepared hand-off (Requirement 20.4, 17.4): NO late fusion implemented here
# ---------------------------------------------------------------------------


def _late_fusion_handoff(*, interview_id: int, recording_id: str) -> None:
    """Stubbed hand-off after ``labeling``; NO aggregation or late fusion here.

    The intended downstream ordering is:
    recording -> multimodal -> text-evaluation -> late-fusion -> feedback-coherence.
    This pipeline deliberately stops after producing per-turn integrated labels.
    Interview-level aggregation and late-fusion scoring are out of scope for this
    feature (Requirement 17.4, 20.4) and must be implemented as a separate stage.
    This function is the single, explicit boundary where that future stage will
    be wired in; today it only records that the boundary was reached.
    """
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=handoff reason=late_fusion_not_implemented",
        interview_id,
        recording_id,
        STAGE_LABELING,
    )
