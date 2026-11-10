"""Orchestrate extraction, derivation and persistence for one interview.

Continuous video is the normal final source; explicitly requested incremental
processing consumes durable clip results. Audio runs before visual models in the
isolated pipeline process. Shared turn_results owns reference populations,
threshold/label assembly and layered JSON; completion/reprocess owns evaluation.
Stage updates remain observable, and unavailable evidence never fabricates data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import Any, Sequence

from app.core.database import SessionLocal
from app.multimodal.turn_results import (
    _assemble_turn_result, _persist_turn, compute_session_references, _OutcomeTracker,
    _context_for, _context_for_speaker, _STUDENT_SPEAKER, _PARAVERBAL_SESSION_FEATURES, _NONVERBAL_SESSION_FEATURES,
    STATUS_COMPLETE, STATUS_PARTIAL, STATUS_UNAVAILABLE,
)
from app.media import get_media_storage
from app.models.medical_interview import (
    InterviewMediaAssetDB,
    InterviewRecordingDB,
    InterviewTurnDB,
    MediaAssetKind,
    MedicalInterviewDB,
    TurnVideoAnalysisDB,
    TurnVideoAnalysisStatus,
)
from app.models.medical_interview.interview_recording import InterviewRecordingSegmentDB
from app.multimodal.constants import NONVERBAL_GAZE_QUEUE_CAPACITY
from app.multimodal.calibration import read_calibration_profile, read_personal_baseline
from app.multimodal.config_loader import (
    ConfigError,
    MethodologyConfig,
    load_methodology_config,
)
from app.multimodal.schemas import MultimodalTurnResult, NonverbalProcessedFeatures, NonverbalRawFeatures, ParaverbalProcessedFeatures, ParaverbalRawFeatures, PersonalBaseline, UnavailableReason
from app.nonverbal.preprocessing import preprocess_nonverbal_turn
from app.nonverbal.video_observations import (
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations_parallel,
    segment_nonverbal_observations_by_turn,
)
from app.nonverbal.ccdbhg import NodAnalysis, analyze_nods
from app.paraverbal.opensmile_extractor import (
    StudentTurnAudio,
    analyze_student_turns,
)
from app.paraverbal.preprocessing import preprocess_paraverbal
from app.utils.runtime_metrics import current_rss_mb, process_id


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
STATUS_FAILED = "failed"

# Public entry point
# ---------------------------------------------------------------------------


async def process_multimodal_interview(
    interview_id: int,
    recording_id: str,
    *,
    use_full_video: bool = False,
) -> None:
    """Run the full multimodal pipeline for one finalized recording.

    Scheduled by the router as a background task
    (``background_tasks.add_task(process_multimodal_interview, ...)``). It owns
    its own DB session and never
    raises to its caller: any unexpected failure is logged and recorded as a
    ``failed`` observation-processing status so the interview is not left in an
    ambiguous state.
    """
    overall_started = perf_counter()
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

        if (recording.capture_config or {}).get('mediaTransport') == 'reusable_blocks_v1':
            from app.multimodal.block_turns import stage_block_turns
            stage_block_turns(db, recording, validate_cache=True)
            db.commit()
        if not use_full_video or any((segment.capture_config or {}).get('mediaTransport') in {'indexed_chunks_v1', 'reusable_blocks_v1'}
                                     for segment in getattr(recording, 'segments', ())):
            await _wait_for_turn_video_jobs(db, interview_id, recording_id)
        _run_pipeline(
            db=db,
            interview=interview,
            recording=recording,
            interview_id=interview_id,
            recording_id=recording_id,
            use_full_video=use_full_video,
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
        logger.info(
            "performance_event component=multimodal_pipeline operation=full_pipeline phase=finished "
            "interview_id=%s recording_id=%s duration_ms=%.3f worker_pid=%s worker_rss_mb=%s",
            interview_id, recording_id, (perf_counter() - overall_started) * 1000,
            process_id(), current_rss_mb(),
        )
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
    use_full_video: bool = False,
) -> None:
    """Execute steps 2-16 of the flow with a single batched commit at the end."""

    pipeline_started = perf_counter()
    phase_started = pipeline_started
    timings_ms: dict[str, float] = {}

    # Step 2: load + validate config once; captured on every turn result.
    config = load_methodology_config()
    versions = config.versions.model_dump()
    config_hash = config.config_hash
    min_turns_for_session_stats = int(
        config.thresholds.get("min_turns_for_session_stats", 0) or 0
    )
    timings_ms["config_load"] = (perf_counter() - phase_started) * 1000
    phase_started = perf_counter()

    # Step 3: read the personal baseline (may be None -> missing_calibration).
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_CALIBRATION)
    segments = getattr(recording, "segments", ())
    profiles = {
        segment.id: read_calibration_profile(interview, segment=segment)
        for segment in segments
    } if segments else {None: read_calibration_profile(interview)}
    baselines = {
        segment.id: read_personal_baseline(interview, segment=segment)
        if profiles[segment.id] is not None else None
        for segment in segments
    } if segments else {None: read_personal_baseline(interview)}
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=%s",
        interview_id,
        recording_id,
        STAGE_CALIBRATION,
        "baseline_available" if any(baselines.values()) else "missing_calibration",
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
    timings_ms["calibration_and_turn_load"] = (perf_counter() - phase_started) * 1000

    # Track whether any modality yielded a usable outcome and whether any gap
    # occurred, to decide complete vs partial vs unavailable at the end.
    outcome = _OutcomeTracker()
    turns_by_segment = _turns_by_segment(segments, turns)
    if sum(map(len, turns_by_segment.values())) < len(turns):
        outcome.note_gap()

    # Step 6: paraverbal extraction (OpenSMILE once per needed student segment).
    phase_started = perf_counter()
    paraverbal_raw: dict[str, ParaverbalRawFeatures] = {}
    cached_visual: dict[str, NonverbalRawFeatures] = {}
    for segment in segments:
        from app.multimodal.block_turns import valid_block_job
        segment_turns = {turn.id: turn for turn in turns_by_segment.get(segment.id, ())}
        for job in db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.recording_id == recording_id).all():
            turn = segment_turns.get(job.turn_id)
            if turn is None or not valid_block_job(job, turn, segment):
                continue
            try:
                cached_visual[turn.id] = NonverbalRawFeatures.model_validate(job.result)
                audio = (job.result.get('extractor') or {}).get('paraverbal_raw')
                if audio is not None and turn.speaker == _STUDENT_SPEAKER:
                    paraverbal_raw[turn.id] = ParaverbalRawFeatures.model_validate(audio)
            except (ValueError, TypeError):
                cached_visual.pop(turn.id, None)
    for segment in segments or (None,):
        segment_id = segment.id if segment is not None else None
        paraverbal_raw.update(_extract_paraverbal(
            db=db,
            recording=recording,
            interview_id=interview_id,
            recording_id=recording_id,
            student_turns=[turn for turn in turns_by_segment.get(segment_id, ())
                           if turn.speaker == _STUDENT_SPEAKER and turn.id not in paraverbal_raw],
            outcome=outcome,
            segment=segment,
        ))
    timings_ms["paraverbal_extraction"] = (perf_counter() - phase_started) * 1000

    # Step 7: paraverbal preprocessing per student turn. Pause segmentation uses
    # the module's technical MIN_PAUSE_MS constant (not a methodology value).
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_PARAVERBAL_PREPROCESSING)
    paraverbal_processed: dict[str, ParaverbalProcessedFeatures] = {}
    phase_started = perf_counter()
    for turn in student_turns:
        raw = paraverbal_raw.get(turn.id)
        if raw is None:
            continue
        paraverbal_processed[turn.id] = preprocess_paraverbal(raw)
    timings_ms["paraverbal_preprocessing"] = (perf_counter() - phase_started) * 1000

    # Step 8: shared MediaPipe/CCDb-HG extraction over the full video.
    phase_started = perf_counter()
    nonverbal_raw: dict[str, NonverbalRawFeatures] = dict(cached_visual)
    nonverbal_context: dict[str, str] = {turn.id: _context_for(turn) for turn in turns if turn.id in cached_visual}
    if use_full_video:
        for segment in segments or (None,):
            segment_id = segment.id if segment is not None else None
            raw, context = _extract_nonverbal(
                db=db, recording=recording, interview_id=interview_id, recording_id=recording_id,
                turns=[turn for turn in turns_by_segment.get(segment_id, ()) if turn.id not in cached_visual], outcome=outcome,
                calibration_profile=profiles[segment_id], use_full_video=True, segment=segment,
            )
            nonverbal_raw.update(raw)
            nonverbal_context.update(context)
    else:
        nonverbal_raw, nonverbal_context = _extract_nonverbal(
            db=db, recording=recording, interview_id=interview_id, recording_id=recording_id,
            turns=[turn for group in turns_by_segment.values() for turn in group], outcome=outcome,
        )
    timings_ms["nonverbal_extraction"] = (perf_counter() - phase_started) * 1000

    # Step 9: nonverbal preprocessing per turn. Gaze tolerance, smile activation,
    # and nod detector parameters are technical constants owned by the nonverbal
    # preprocessing module, so no methodology config is threaded here.
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_NONVERBAL_PREPROCESSING)
    nonverbal_processed: dict[str, NonverbalProcessedFeatures] = {}
    nonverbal_reasons: dict[str, dict[str, UnavailableReason]] = {}
    phase_started = perf_counter()
    for turn in turns:
        raw = nonverbal_raw.get(turn.id)
        if raw is None:
            continue
        result = preprocess_nonverbal_turn(
            raw,
            nonverbal_context.get(turn.id, _context_for(turn)),
            baseline=baselines.get(getattr(turn, "segment_id", None)),
        )
        nonverbal_processed[turn.id] = result.processed
        nonverbal_reasons[turn.id] = result.reasons
    timings_ms["nonverbal_preprocessing"] = (perf_counter() - phase_started) * 1000

    # Step 10: compute SessionReferences once (two-pass, guarded).
    para_session_refs = compute_session_references(
        processed_by_turn=paraverbal_processed,
        raw_by_turn=paraverbal_raw,
        feature_names=_PARAVERBAL_SESSION_FEATURES,
        min_turns=min_turns_for_session_stats,
    )
    nonverbal_session_refs = {speaker: compute_session_references(
        processed_by_turn={turn.id: nonverbal_processed[turn.id]
                           for turn in turns if turn.speaker == speaker and turn.id in nonverbal_processed},
        raw_by_turn=nonverbal_raw,
        feature_names=_NONVERBAL_SESSION_FEATURES,
        min_turns=min_turns_for_session_stats,
    ) for speaker in ("student", "patient")}
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

    from app.multimodal.extraction_provenance import build_extraction_manifest, record_extraction_manifest
    calibration = {
        segment_id: {"baseline": baseline.model_dump() if baseline is not None else None,
                     "profile": profiles[segment_id]}
        for segment_id, baseline in baselines.items()
    }
    manifest = build_extraction_manifest(config, mode="continuous" if use_full_video else "stored_visual",
        references={"paraverbal": para_session_refs, "nonverbal_by_speaker": nonverbal_session_refs},
        calibration=calibration if segments else calibration[None])
    manifest_hash = record_extraction_manifest(recording, manifest)
    for raw in paraverbal_raw.values():
        raw.extractor = {**raw.extractor, "extraction_manifest_hash": manifest_hash,
                         "labeling_manifest_hash": manifest_hash}
    for raw in nonverbal_raw.values():
        metadata = dict(raw.extractor)
        stored_manifest = metadata.pop("extraction_manifest", None)
        if metadata.get('continuous_capture') and stored_manifest is not None:
            metadata['extraction_manifest_hash'] = record_extraction_manifest(recording, stored_manifest)
        elif use_full_video:
            metadata["extraction_manifest_hash"] = manifest_hash
        elif stored_manifest is not None:
            metadata["extraction_manifest_hash"] = record_extraction_manifest(recording, stored_manifest)
        elif "extraction_manifest_hash" not in metadata:
            metadata["extraction_provenance"] = "legacy_unavailable"
        metadata["labeling_manifest_hash"] = manifest_hash
        raw.extractor = metadata

    # Steps 11-13: threshold + label + assemble per turn.
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_THRESHOLDING)
    phase_started = perf_counter()
    results: list[tuple[InterviewTurnDB, MultimodalTurnResult]] = []
    for turn in turns:
        result = _assemble_turn_result(
            turn=turn,
            config=config,
            versions=versions,
            config_hash=config_hash,
            baseline_available=baselines.get(getattr(turn, "segment_id", None)) is not None,
            paraverbal_raw=paraverbal_raw.get(turn.id),
            paraverbal_processed=paraverbal_processed.get(turn.id),
            para_session_refs=para_session_refs,
            nonverbal_raw=nonverbal_raw.get(turn.id),
            nonverbal_processed=nonverbal_processed.get(turn.id),
            nonverbal_reasons=nonverbal_reasons.get(turn.id, {}),
            nonverbal_session_refs=nonverbal_session_refs.get(turn.speaker),
            outcome=outcome,
        )
        results.append((turn, result))
    timings_ms["thresholding_and_labeling"] = (perf_counter() - phase_started) * 1000

    _set_stage(db, recording, STATUS_PROCESSING, STAGE_LABELING)

    # Evaluation remains owned by completion/reprocessing after observations finish.
    _late_fusion_handoff(interview_id=interview_id, recording_id=recording_id)

    # Steps 13-14: batch-persist all per-turn layered results in one commit.
    phase_started = perf_counter()
    for turn, result in results:
        _persist_turn(turn, result)
    db.commit()
    timings_ms["persistence"] = (perf_counter() - phase_started) * 1000
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
    logger.info(
        "performance_event component=multimodal_pipeline operation=stages phase=complete "
        "interview_id=%s recording_id=%s duration_ms=%.3f turn_count=%s student_turn_count=%s "
        "timings_ms=%s worker_pid=%s worker_rss_mb=%s",
        interview_id, recording_id, (perf_counter() - pipeline_started) * 1000,
        len(turns), len(student_turns), json.dumps(timings_ms, sort_keys=True),
        process_id(), current_rss_mb(),
    )


# ---------------------------------------------------------------------------
# Extraction stages
# ---------------------------------------------------------------------------


def _turns_by_segment(segments, turns) -> dict[str | None, list[InterviewTurnDB]]:
    if not segments:
        return {None: [turn for turn in turns if getattr(turn, "segment_id", None) is None]}
    by_id = {segment.id: segment for segment in segments}
    groups: dict[str | None, list[InterviewTurnDB]] = {}
    for turn in turns:
        segment = by_id.get(turn.segment_id)
        if (segment is not None and segment.duration_ms is not None
                and segment.offset_ms <= turn.start_ms < turn.end_ms <= segment.offset_ms + segment.duration_ms):
            groups.setdefault(segment.id, []).append(turn)
    return groups


def _extract_paraverbal(
    *,
    db: Any,
    recording: InterviewRecordingDB,
    interview_id: int,
    recording_id: str,
    student_turns: Sequence[InterviewTurnDB],
    outcome: "_OutcomeTracker",
    segment: InterviewRecordingSegmentDB | None = None,
) -> dict[str, ParaverbalRawFeatures]:
    """Run OpenSMILE once over the needed student segments (Requirement 19.2).

    Returns a mapping of ``turn_id -> ParaverbalRawFeatures`` for turns that yielded a usable signal;
    turns absent from the mapping are treated downstream as unavailable. An
    extractor exception marks the paraverbal modality as an extractor failure
    without failing the whole run (Requirement 24.2).
    """
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_PARAVERBAL_EXTRACTION)
    if not student_turns:
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=paraverbal result=skipped reason=%s",
            interview_id,
            recording_id,
            STAGE_PARAVERBAL_EXTRACTION,
            "no_student_turns",
        )
        return {}

    storage = get_media_storage()
    asset = _ready_asset(db, recording.id, MediaAssetKind.STUDENT_AUDIO.value,
                         segment.id if segment is not None else None)
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
        offset_ms = segment.offset_ms if segment is not None else 0
        windows = [
            StudentTurnAudio(
                turn_id=turn.id,
                start_ms=turn.start_ms - offset_ms,
                end_ms=turn.end_ms - offset_ms,
                transcript=turn.transcript,
                message_id=getattr(turn, 'message_id', None),
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
    calibration_profile: dict | None = None,
    use_full_video: bool = False,
    segment: InterviewRecordingSegmentDB | None = None,
) -> tuple[dict[str, NonverbalRawFeatures], dict[str, str]]:
    """Load turn jobs, or explicitly recover from the canonical full video."""
    _set_stage(db, recording, STATUS_PROCESSING, STAGE_NONVERBAL_EXTRACTION)
    if not turns:
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
            "modality=nonverbal result=skipped reason=%s",
            interview_id,
            recording_id,
            STAGE_NONVERBAL_EXTRACTION,
            "no_turns",
        )
        return {}, {}

    if not use_full_video:
        jobs = db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.recording_id == recording_id
        ).all()
        jobs_by_turn = {job.turn_id: job for job in jobs}
        raw_by_turn: dict[str, NonverbalRawFeatures] = {}
        context_by_turn: dict[str, str] = {}
        for turn in turns:
            job = jobs_by_turn.get(turn.id)
            if (
                job is None
                or job.status != TurnVideoAnalysisStatus.COMPLETED.value
                or not job.result
            ):
                outcome.note_gap()
                continue
            try:
                raw_by_turn[turn.id] = NonverbalRawFeatures.model_validate(job.result)
                context_by_turn[turn.id] = _context_for_speaker(turn.speaker)
            except Exception:  # noqa: BLE001 - malformed durable result is unavailable.
                outcome.note_gap()
                logger.exception(
                    "multimodal_pipeline interview_id=%s turn_id=%s modality=nonverbal result=invalid_turn_job",
                    interview_id, turn.id,
                )
        logger.info(
            "multimodal_pipeline interview_id=%s recording_id=%s stage=%s modality=nonverbal "
            "source=turn_jobs turn_count=%s observed=%s",
            interview_id, recording_id, STAGE_NONVERBAL_EXTRACTION, len(turns), len(raw_by_turn),
        )
        return raw_by_turn, context_by_turn

    storage = get_media_storage()
    asset = _ready_asset(db, recording.id, MediaAssetKind.STUDENT_VIDEO.value,
                         segment.id if segment is not None else None)
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
        source = segment if segment is not None else recording
        offset_ms = segment.offset_ms if segment is not None else 0
        windows = [
            TurnWindow(
                turn_id=turn.id,
                start_ms=turn.start_ms - offset_ms,
                end_ms=turn.end_ms - offset_ms,
                conversation_speaker=turn.speaker,
            )
            for turn in turns
        ]
        profile = calibration_profile
        observations = extract_nonverbal_video_observations_parallel(
            video_path,
            queue_capacity=NONVERBAL_GAZE_QUEUE_CAPACITY,
            calibration_profile=profile,
        )
        segmented = segment_nonverbal_observations_by_turn(observations, windows)
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
    windows_by_id = {window.turn_id: window for window in windows}
    for turn_id, turn_observations in segmented.items():
        try:
            try:
                local_nods = analyze_nods([item.shared for item in turn_observations])
            except Exception:  # noqa: BLE001 - preserve the other visual branches.
                logger.exception("multimodal_pipeline turn_id=%s branch=ccdbhg result=extractor_failure", turn_id)
                local_nods = NodAnalysis((), False, "extractor_failure")
            raw_by_turn[turn_id] = build_turn_raw_features(
                turn_observations,
                windows_by_id[turn_id],
                nod_analysis=local_nods,
                calibration_profile=profile,
                patient_roi_snapshots=(source.capture_config or {}).get("patientRoiSnapshots", []),
                interaction_area_snapshots=(source.capture_config or {}).get("interactionAreaSnapshots", []),
                roi_duration_ms=source.duration_ms,
            )
            raw_by_turn[turn_id].extractor["source"] = "full_session_video"
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
        context_by_turn[turn_id] = _context_for_speaker(
            windows_by_id[turn_id].conversation_speaker
        )

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


async def _wait_for_turn_video_jobs(
    db: Any, interview_id: int, recording_id: str, timeout_seconds: float = 21600.0
) -> None:
    """Wait only for durable queued/processing turn jobs before final assembly."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        db.expire_all()
        jobs = db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.recording_id == recording_id,
            TurnVideoAnalysisDB.medical_interview_id == interview_id,
        ).all()
        pending_statuses = {
            TurnVideoAnalysisStatus.QUEUED.value,
            TurnVideoAnalysisStatus.PROCESSING.value,
        }
        pending = [job for job in jobs if job.status in pending_statuses]
        if not pending:
            return
        if loop.time() >= deadline:
            logger.error(
                "multimodal_pipeline interview_id=%s recording_id=%s result=turn_job_timeout pending=%s",
                interview_id, recording_id, len(pending),
            )
            raise TimeoutError("Turn video analysis did not finish before the deadline")
        await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# Recording lifecycle updates


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
    pending_manifests = dict((recording.capture_config or {}).get("extraction_manifests", {}))
    with db.no_autoflush:
        db.refresh(recording, attribute_names=["capture_config"], with_for_update=True)
    capture_config = dict(recording.capture_config or {})
    if pending_manifests:
        capture_config["extraction_manifests"] = {
            **capture_config.get("extraction_manifests", {}), **pending_manifests,
        }
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
    segment_id: str | None = None,
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
            InterviewMediaAssetDB.segment_id == segment_id,
            InterviewMediaAssetDB.status == "ready",
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Outcome taxonomy (Requirement 18, 24.2): complete / partial / unavailable
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Prepared hand-off (Requirement 20.4, 17.4): NO late fusion implemented here
# ---------------------------------------------------------------------------


def _late_fusion_handoff(*, interview_id: int, recording_id: str) -> None:
    """Record the label boundary; completion/reprocess owns LLM evaluation.

    The observation pipeline does not score performance. Its caller waits for
    terminal observations and delegates to the separate evaluation service.
    """
    logger.info(
        "multimodal_pipeline interview_id=%s recording_id=%s stage=%s "
        "result=handoff reason=evaluation_owned_by_orchestrator",
        interview_id,
        recording_id,
        STAGE_LABELING,
    )
