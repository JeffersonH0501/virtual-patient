"""Stored-feature maintenance must reproduce the pipeline and mark old feedback stale."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session, sessionmaker
from fastapi import HTTPException
import pytest
from scripts import relabel_multimodal as relabel
from app.multimodal import turn_results
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.schemas import NonverbalProcessedFeatures
from app.multimodal.tests.test_reference_integrity import raw
from app.models.medical_interview import InterviewTurnDB, InterviewRecordingDB, MedicalInterviewDB, InterviewStatus
from app.routers.tests.test_lifecycle_integrity import lifecycle_api


def test_relabel_masks_low_quality_exactly_like_pipeline():
    config = load_methodology_config()
    source = raw(False)
    processed = NonverbalProcessedFeatures(mean_smile_activation=.4, smile_activity_ratio=1, context="listening")
    old = {"raw": source.model_dump(), "processed": processed.model_dump(), "quality": source.video_quality,
        "base_labels": {}, "integrated_labels": {}, "status": "ok", "reason": None}
    refs = {"mean_smile_activation": {"p25": .175, "p75": .325}}
    expected = turn_results._layer_to_json(turn_results._nonverbal_layer(config=config, baseline_available=True,
        raw=source, processed=processed, reasons={}, session_refs=refs, outcome=turn_results._OutcomeTracker()),
        versions=config.versions.model_dump(), config_hash=config.config_hash)
    actual = relabel._relabel_nonverbal_layer(old, processed, config, baseline_available=True, session_refs=refs)
    assert actual == expected


def test_relabel_uses_context_references_and_marks_results_stale_atomically(lifecycle_api, monkeypatch):
    state = lifecycle_api
    config = load_methodology_config()
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = InterviewStatus.COMPLETED
        interview.start_time = datetime.now(timezone.utc)
        db.add(InterviewRecordingDB(medical_interview_id=state.id, status="partial", started_at=interview.start_time,
            consent_policy_version="synthetic", capture_config={"evaluation_processing": {"status": "complete"}}))
        for index, value in enumerate([.1,.2,.3,.4,.6,.7,.8,.9,1.]):
            source = raw(index != 8)
            speaker = "student" if index < 4 else "patient"
            processed = NonverbalProcessedFeatures(mean_smile_activation=value, smile_activity_ratio=1,
                context="speaking" if speaker == "student" else "listening")
            db.add(InterviewTurnDB(medical_interview_id=state.id, speaker=speaker, sequence=index,
                start_ms=index*1000, end_ms=(index+1)*1000, transcript="Synthetic", input_source="synthetic",
                timing_source="synthetic", timing_quality="measured", nonverbal_features={
                    "raw": source.model_dump(), "processed": processed.model_dump(), "quality": source.video_quality,
                    "base_labels": {}, "integrated_labels": {}, "status": "ok", "reason": None}))
        db.commit()
    monkeypatch.setattr(relabel, "SessionLocal", sessionmaker(bind=state.engine))
    relabel.relabel([state.id])
    with Session(state.engine) as db:
        turns = db.query(InterviewTurnDB).order_by(InterviewTurnDB.sequence).all()
        assert turns[3].nonverbal_features["processed"]["mean_smile_activation"] == .4
        assert turns[8].nonverbal_features["integrated_labels"]["smile_activity"]["status"] == "unavailable"
        assert db.query(InterviewRecordingDB).one().capture_config["evaluation_processing"]["status"] == "stale"
        assert db.query(InterviewRecordingDB).one().capture_config["observation_processing"]["status"] == "partial"
        first = [turn.nonverbal_features for turn in turns]
    relabel.relabel([state.id])
    with Session(state.engine) as db:
        assert [turn.nonverbal_features for turn in db.query(InterviewTurnDB).order_by(InterviewTurnDB.sequence)] == first


def test_relabel_rejects_recording_lock_contention_before_writing(lifecycle_api, monkeypatch):
    state = lifecycle_api
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = InterviewStatus.COMPLETED
        db.add(InterviewRecordingDB(medical_interview_id=state.id, status="partial",
            started_at=datetime.now(timezone.utc), consent_policy_version="synthetic", capture_config={}))
        db.commit()
    monkeypatch.setattr(relabel, "SessionLocal", sessionmaker(bind=state.engine))
    with Session(state.engine) as competing:
        competing.query(InterviewRecordingDB).with_for_update().one()
        with pytest.raises(HTTPException) as error:
            relabel.relabel([state.id])
        assert error.value.status_code == 503
        assert error.value.detail["code"] == "capture_busy"
