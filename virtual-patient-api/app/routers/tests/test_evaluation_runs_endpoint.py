"""The full-prompt dialog reads only the latest evaluation run of each condition."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.medical_interview.interview_evaluation import InterviewEvaluationRunDB
from app.models.user import UserRole
from app.routers import interview_recordings as module

INTERVIEW = 6837


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    InterviewEvaluationRunDB.__table__.create(engine)
    monkeypatch.setattr(module, "_get_interview", lambda session, interview_id: object())
    monkeypatch.setattr(module, "_require_replay_access", lambda interview, user: None)
    monkeypatch.setattr(module, "require_assessments", lambda session, interview, user: None)
    base = datetime(2026, 11, 16, tzinfo=timezone.utc)
    with Session(engine) as session:
        # Three regenerations of each condition; each snapshot carries the bulky per-turn evidence copy.
        for generation in range(3):
            for condition in ("TEXT_ONLY", "TEXT_PLUS_MULTIMODAL"):
                session.add(InterviewEvaluationRunDB(
                    id=f"{condition}-{generation}", medical_interview_id=INTERVIEW, evaluation_condition=condition,
                    created_at=base + timedelta(hours=generation),
                    snapshot={"generation": generation,
                              "inputs": {"evidence": ["bulky"] * 50, "prompts": {"show_interest": "prompt"}},
                              "provider_responses": [{"aspect": "show_interest", "prompt_messages": [{"role": "system"}]}]}))
        session.commit()
        yield session


def call(db, role):
    return module.read_evaluation_runs(INTERVIEW, SimpleNamespace(role=role), db)


def test_admin_receives_only_the_latest_run_of_each_condition_without_the_evidence_copy(db):
    runs = call(db, UserRole.ADMIN)
    assert [(run["condition"], run["snapshot"]["generation"]) for run in runs] == [
        ("TEXT_ONLY", 2), ("TEXT_PLUS_MULTIMODAL", 2)]
    assert all("evidence" not in run["snapshot"]["inputs"] for run in runs)
    assert runs[0]["snapshot"]["inputs"]["prompts"] == {"show_interest": "prompt"}


def test_student_receives_only_the_latest_multimodal_run_without_prompts(db):
    runs = call(db, UserRole.STUDENT)
    assert [(run["id"], run["condition"]) for run in runs] == [("TEXT_PLUS_MULTIMODAL-2", "TEXT_PLUS_MULTIMODAL")]
    assert "prompts" not in runs[0]["snapshot"]["inputs"]
    assert "prompt_messages" not in runs[0]["snapshot"]["provider_responses"][0]


def test_older_snapshots_are_never_read(db):
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    call(db, UserRole.ADMIN)
    selecting_snapshots = [statement for statement in statements if "snapshot" in statement]
    # The history is scanned by ID only; the snapshot column is selected once, for the two latest rows.
    assert len(selecting_snapshots) == 1
    assert "IN (" in selecting_snapshots[0]


def test_an_interview_without_runs_returns_nothing(db):
    assert module.read_evaluation_runs(1, SimpleNamespace(role=UserRole.ADMIN), db) == []
