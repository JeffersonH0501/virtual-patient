"""Synthetic dependency deletion and crash recovery against the existing database."""
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.controllers.administrative_deletion import delete_parent, recover_staged_media
from app.models.clinical_case import ClinicalCaseDB, CaseType
from app.models.user import UserDB, UserRole
from app.models.medical_interview import MedicalInterviewDB, InterviewStatus
from app.models.teacher_grading import TeacherAssignmentDB, TeacherRatingDB
from app.routers.tests.test_organization_interview_history import history_api


@pytest.fixture
def deletion_data(history_api, tmp_path):
    client, actor, organization, _ = history_api
    db = client.history_db
    student = UserDB(name="Deletion student", email=uuid4().hex + "@example.org", hashed_password="unused", role=UserRole.STUDENT, organization_id=organization)
    teacher = UserDB(name="Deletion teacher", email=uuid4().hex + "@example.org", hashed_password="unused", role=UserRole.TEACHER, organization_id=organization)
    db.add_all([student, teacher]); db.flush()
    case = ClinicalCaseDB(title="Deletion case", description="Synthetic", case_type=CaseType.CUSTOM, organization_id=organization, created_by=teacher.id)
    db.add(case); db.flush()
    interview = MedicalInterviewDB(user_id=student.id, clinical_case_id=case.id, status=InterviewStatus.COMPLETED)
    db.add(interview); db.flush()
    assignment = TeacherAssignmentDB(interview_id=interview.id, teacher_id=teacher.id, assigned_by_id=actor.id)
    db.add(assignment); db.flush()
    db.add(TeacherRatingDB(assignment_id=assignment.id, rubric_version="test", rubric_snapshot={}, results=[], submitted_at=interview.created_at))
    db.commit()
    media = tmp_path / "interviews" / str(interview.id)
    media.mkdir(parents=True)
    (media / "synthetic.txt").write_text("synthetic media placeholder")
    with patch("app.controllers.administrative_deletion.get_media_storage", return_value=SimpleNamespace(root=tmp_path)):
        yield db, student, teacher, case, interview, media, tmp_path


@pytest.mark.parametrize("kind", ["user", "case"])
def test_parent_removes_interviews_ratings_and_media(deletion_data, kind):
    db, student, teacher, case, interview, media, _ = deletion_data
    interview_id = interview.id
    delete_parent(db, student if kind == "user" else case, kind)
    db.expire_all()
    assert db.get(MedicalInterviewDB, interview_id) is None
    assert db.query(TeacherAssignmentDB).filter_by(interview_id=interview_id).count() == 0
    assert not media.exists()


def test_deleting_teacher_removes_submitted_ratings_and_preserves_cases(deletion_data):
    db, _, teacher, case, interview, media, _ = deletion_data
    teacher_id, case_id = teacher.id, case.id
    delete_parent(db, teacher, "user")
    db.expire_all()
    assert db.get(UserDB, teacher_id) is None
    assert db.get(ClinicalCaseDB, case_id).created_by is None
    assert db.query(TeacherAssignmentDB).filter_by(teacher_id=teacher_id).count() == 0
    assert media.exists()


def test_pending_interview_blocks_deletion(deletion_data):
    db, student, _, _, interview, media, _ = deletion_data
    interview.status = InterviewStatus.IN_PROGRESS
    db.commit()
    with pytest.raises(HTTPException) as failure:
        delete_parent(db, student, "user")
    assert failure.value.status_code == 409
    assert media.exists()


def test_discarded_unstarted_calibration_does_not_block_user_deletion(deletion_data):
    db, student, _, _, interview, media, _ = deletion_data
    interview.status = InterviewStatus.IN_PROGRESS
    interview.start_time = None
    interview.interview_metadata = {"calibration_discarded": True}
    db.commit()
    user_id = student.id
    delete_parent(db, student, "user")
    assert db.get(UserDB, user_id) is None
    assert not media.exists()


def test_failed_commit_restores_media_and_database(deletion_data):
    db, student, _, _, interview, media, _ = deletion_data
    interview_id = interview.id
    with patch.object(db, "commit", side_effect=RuntimeError("Synthetic commit failure")):
        with pytest.raises(HTTPException) as failure:
            delete_parent(db, student, "user")
    assert failure.value.status_code == 500
    assert db.get(MedicalInterviewDB, interview_id) is not None
    assert (media / "synthetic.txt").exists()


def test_restart_restores_staging_if_transaction_never_committed(deletion_data):
    db, _, _, _, interview, media, root = deletion_data
    folder = root / ".deletions" / "synthetic-restart"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("[" + str(interview.id) + "]")
    media.rename(folder / str(interview.id))
    recover_staged_media(db)
    assert media.exists()
    assert not folder.exists()


def test_case_mutations_are_removed_and_user_deletion_stays_restricted(deletion_data, history_api):
    from app.routers import clinical_cases, users
    client, actor, organization, other = history_api
    client.app.include_router(clinical_cases.router)
    client.app.include_router(users.router)
    db, student, _, case, _, media, _ = deletion_data
    actor.role = UserRole.TEACHER
    assert client.delete(f"/clinical-cases/{case.id}").status_code == 405
    assert client.delete(f"/users/admin/{student.id}").status_code == 403
    actor.role = UserRole.SUPERUSER
    actor.organization_id = other
    assert client.delete(f"/clinical-cases/{case.id}").status_code == 405
    assert client.delete(f"/users/admin/{student.id}").status_code == 404
    assert client.get(f"/clinical-cases/{case.id}").status_code == 404
    actor.organization_id = organization
    assert client.post(f"/clinical-cases/{case.id}", json={"organization_id": None}).status_code == 405
    assert client.delete(f"/users/admin/{student.id}").status_code == 204
    assert not media.exists()


def test_default_cases_cannot_be_deleted(deletion_data, history_api):
    from app.routers import clinical_cases
    client, _, _, _ = history_api
    client.app.include_router(clinical_cases.router)
    db, _, _, case, _, media, _ = deletion_data
    case.case_type = CaseType.DEFAULT
    db.commit()
    assert client.delete(f"/clinical-cases/{case.id}").status_code == 405
    assert media.exists()


def test_pending_automatic_jobs_block_parent_deletion(deletion_data):
    from app.models.processing_job import InterviewProcessingJobDB
    db, _, _, case, interview, media, _ = deletion_data
    db.add(InterviewProcessingJobDB(medical_interview_id=interview.id, kind="evaluation", status="queued", payload={}))
    db.commit()
    with pytest.raises(HTTPException) as failure:
        delete_parent(db, case, "case")
    assert failure.value.status_code == 409
    assert media.exists()
