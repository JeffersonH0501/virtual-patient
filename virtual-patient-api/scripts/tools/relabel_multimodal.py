#!/usr/bin/env python3
"""Explicit maintenance: relabel frozen stored features through the pipeline policy.

No extraction, evaluation calls, or automatic historical migration occurs.
Each interview commits atomically and marks existing feedback stale when changed.
"""
from __future__ import annotations

import argparse

from app.core.database import SessionLocal
from app.controllers.interview_lifecycle import lock_row
from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB, InterviewTurnDB, TurnVideoAnalysisDB
from app.models.processing_job import InterviewProcessingJobDB
from app.multimodal.calibration import read_personal_baseline
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.turn_results import (
    _NONVERBAL_SESSION_FEATURES, _PARAVERBAL_SESSION_FEATURES,
    _OutcomeTracker, _paraverbal_layer, _nonverbal_layer, _layer_to_json,
    compute_session_references,
)
from app.multimodal.schemas import (
    NonverbalProcessedFeatures, ParaverbalProcessedFeatures,
    NonverbalRawFeatures, ParaverbalRawFeatures, UnavailableReason,
)


def _collect_features(turns, column, model, *, block, student_only):
    features = {}
    for turn in turns:
        if student_only and turn.speaker != "student":
            continue
        layer = getattr(turn, column)
        if isinstance(layer, dict) and isinstance(layer.get(block), dict):
            features[turn.id] = model.model_validate(layer[block])
    return features


def _relabel_paraverbal_layer(layer, processed, config, *, baseline_available, session_refs, outcome=None):
    result = _paraverbal_layer(config=config, baseline_available=baseline_available,
        raw=ParaverbalRawFeatures.model_validate(layer["raw"]), processed=processed,
        session_refs=session_refs, outcome=outcome or _OutcomeTracker())
    return _layer_to_json(result, versions=config.versions.model_dump(), config_hash=config.config_hash)


def _relabel_nonverbal_layer(layer, processed, config, *, baseline_available, session_refs, outcome=None):
    reasons = {key: UnavailableReason(value) for key, value in
               (layer.get("quality") or {}).get("feature_reasons", {}).items()}
    result = _nonverbal_layer(config=config, baseline_available=baseline_available,
        raw=NonverbalRawFeatures.model_validate(layer["raw"]), processed=processed, reasons=reasons,
        session_refs=session_refs, outcome=outcome or _OutcomeTracker())
    return _layer_to_json(result, versions=config.versions.model_dump(), config_hash=config.config_hash)


def relabel(interview_ids: list[int]) -> None:
    """Relabel only explicitly selected, completed and idle interviews."""
    config = load_methodology_config()
    min_turns = int(config.thresholds.get("min_turns_for_session_stats", 0) or 0)
    with SessionLocal() as db:
        for interview_id in interview_ids:
            try:
                interview = lock_row(db, MedicalInterviewDB, interview_id)
                if interview is None:
                    print(f"Interview {interview_id}: skipped (interview not found)", flush=True)
                    db.rollback()
                    continue
                if getattr(interview.status, "value", interview.status) != "completed":
                    raise ValueError("Only completed interviews can be relabeled")
                recording = interview.recording
                if recording is not None:
                    recording = lock_row(db, InterviewRecordingDB, recording.id)
                active_job = db.query(InterviewProcessingJobDB).filter(
                    InterviewProcessingJobDB.medical_interview_id == interview_id,
                    InterviewProcessingJobDB.status.in_(["queued", "processing"])).first()
                active_clip = db.query(TurnVideoAnalysisDB).filter(
                    TurnVideoAnalysisDB.medical_interview_id == interview_id,
                    TurnVideoAnalysisDB.status.in_(["queued", "processing"])).first()
                capture = (recording.capture_config or {}) if recording is not None else {}
                if active_job or active_clip or any(capture.get(key, {}).get("status") in {"queued", "processing"}
                        for key in ("observation_processing", "evaluation_processing")):
                    raise ValueError("Interview processing must finish before relabeling")
                turns = db.query(InterviewTurnDB).filter(
                    InterviewTurnDB.medical_interview_id == interview_id).order_by(InterviewTurnDB.sequence).all()
                baseline_available = read_personal_baseline(interview) is not None
                para = _collect_features(turns, "paraverbal", ParaverbalProcessedFeatures, block="processed", student_only=True)
                para_raw = _collect_features(turns, "paraverbal", ParaverbalRawFeatures, block="raw", student_only=True)
                visual = _collect_features(turns, "nonverbal_features", NonverbalProcessedFeatures, block="processed", student_only=False)
                visual_raw = _collect_features(turns, "nonverbal_features", NonverbalRawFeatures, block="raw", student_only=False)
                para_refs = compute_session_references(processed_by_turn=para, raw_by_turn=para_raw,
                    feature_names=_PARAVERBAL_SESSION_FEATURES, min_turns=min_turns)
                visual_refs = {speaker: compute_session_references(
                    processed_by_turn={turn.id: visual[turn.id] for turn in turns if turn.speaker == speaker and turn.id in visual},
                    raw_by_turn=visual_raw, feature_names=_NONVERBAL_SESSION_FEATURES, min_turns=min_turns)
                    for speaker in ("student", "patient")}
                changed = 0
                outcome = _OutcomeTracker()
                for turn in turns:
                    for column, processed, refs, operation in (
                        ("paraverbal", para, para_refs, _relabel_paraverbal_layer),
                        ("nonverbal_features", visual, visual_refs.get(turn.speaker), _relabel_nonverbal_layer),
                    ):
                        if turn.id not in processed:
                            if column != "paraverbal" or turn.speaker == "student":
                                outcome.note_gap()
                            continue
                        previous = getattr(turn, column)
                        updated = operation(previous, processed[turn.id], config,
                            baseline_available=baseline_available, session_refs=refs, outcome=outcome)
                        if updated != previous:
                            setattr(turn, column, updated)
                            changed += 1
                if changed and recording is not None:
                    recording.capture_config = {**capture, "observation_processing": {
                        **capture.get("observation_processing", {}), "status": outcome.final_status(), "stage": "finished"},
                        "evaluation_processing": {
                        **capture.get("evaluation_processing", {}), "status": "stale", "reason": "labels_regenerated"},
                        "learning_moments": {**capture.get("learning_moments", {}), "status": "stale", "reason": "labels_regenerated"}}
                db.commit()
                print(f"Interview {interview_id}: relabeled_layers={changed} config_hash={config.config_hash[:12]}", flush=True)
            except Exception:
                db.rollback()
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relabel explicitly selected completed interviews from stored features.")
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    relabel(parse_args().interview_ids)
