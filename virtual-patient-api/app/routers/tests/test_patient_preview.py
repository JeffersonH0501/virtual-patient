from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from langchain_core.messages import AIMessage
from fastapi.testclient import TestClient
import pytest

from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.clinical_case import CaseType
from app.models.user import UserRole
from app.routers import clinical_cases, speech


@pytest.mark.parametrize("role, expected_status", [
    (UserRole.STUDENT, 403),
    (UserRole.TEACHER, 403),
    (UserRole.SUPERUSER, 200),
])
def test_patient_preview_requires_superuser(monkeypatch, role, expected_status):
    app = FastAPI()
    app.include_router(clinical_cases.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=role)
    case = SimpleNamespace(active=True, case_type=CaseType.DEFAULT, female_name="Patient")
    db = Mock()
    db.get.side_effect = [case, SimpleNamespace(namespace_key="friendly_polite")]
    app.dependency_overrides[get_db] = lambda: db
    workflow = Mock()
    workflow.process_interview_message = AsyncMock(return_value={
        "translated_patient_response": "Me duelen las manos.",
    })
    factory = Mock(return_value=workflow)
    monkeypatch.setattr(clinical_cases, "VirtualPatientWorkflow", factory)

    with TestClient(app) as client:
        response = client.post("/clinical-cases/5/patient-preview", json={
            "question": "  ¿Qué le duele?  ",
            "language": "es",
            "gender": "female",
            "personality_id": 1,
        })

    assert response.status_code == expected_status
    if role != UserRole.SUPERUSER:
        db.get.assert_not_called()
        factory.assert_not_called()
        return
    assert response.json() == {"answer": "Me duelen las manos."}
    assert factory.call_args.kwargs["persist_background_memory"] is False
    assert factory.call_args.kwargs["patient_gender"] == "female"
    assert factory.call_args.kwargs["personality"] == "friendly_polite"
    workflow.process_interview_message.assert_awaited_once_with(
        question={"role": "user", "content": "¿Qué le duele?"},
        clinical_case=case,
        history=[AIMessage(content="Hola, mucho gusto.")],
    )
    db.commit.assert_not_called()


@pytest.mark.parametrize("role, expected_status", [(UserRole.STUDENT, 403), (UserRole.SUPERUSER, 200)])
def test_preview_speech_uses_selected_voice_without_saving(monkeypatch, role, expected_status):
    app = FastAPI()
    app.include_router(clinical_cases.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=role)
    db = Mock()
    db.get.side_effect = [
        SimpleNamespace(active=True, case_type=CaseType.DEFAULT),
        SimpleNamespace(namespace_key="friendly_polite"),
    ]
    app.dependency_overrides[get_db] = lambda: db
    speech = Mock()
    speech.synthesize_patient_message.return_value = SimpleNamespace(
        content=b"test mp3", content_type="audio/mpeg",
    )
    monkeypatch.setattr(clinical_cases, "SpeechService", lambda: speech)

    with TestClient(app) as client:
        response = client.post("/clinical-cases/5/patient-preview/speech", json={
            "text": "Hola", "gender": "female", "personality_id": 1,
        })

    assert response.status_code == expected_status
    if role == UserRole.SUPERUSER:
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.content == b"test mp3"
        speech.synthesize_patient_message.assert_called_once_with("Hola", "friendly_polite", "female")
        db.commit.assert_not_called()
    else:
        speech.synthesize_patient_message.assert_not_called()


@pytest.mark.parametrize("role, expected_status", [(UserRole.STUDENT, 403), (UserRole.SUPERUSER, 200)])
def test_preview_summary_extracts_conversation_without_saving(monkeypatch, role, expected_status):
    app = FastAPI()
    app.include_router(clinical_cases.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=role)
    case = SimpleNamespace(active=True, case_type=CaseType.DEFAULT)
    db = Mock()
    db.get.return_value = case
    app.dependency_overrides[get_db] = lambda: db
    process_summary = AsyncMock(return_value={"translated_summary": {"summary_text": "Dolor de manos."}})
    workflow = Mock(return_value=SimpleNamespace(process_summary=process_summary))
    monkeypatch.setattr(clinical_cases, "create_summary_workflow", workflow)

    with TestClient(app) as client:
        response = client.post("/clinical-cases/5/patient-preview/summary", json={
            "language": "es",
            "history": [{"question": "¿Qué le duele?", "answer": "Las manos."}],
        })

    assert response.status_code == expected_status
    if role == UserRole.SUPERUSER:
        assert response.json()["summary_text"] == "Dolor de manos."
        process_summary.assert_awaited_once_with(
            messages=[
                {"role": "user", "content": "¿Qué le duele?"},
                {"role": "assistant", "content": "Las manos."},
            ],
            clinical_case=case,
        )
        db.commit.assert_not_called()
    else:
        workflow.assert_not_called()

def test_preview_progressive_audio_keeps_voice_policy_and_closes_provider(monkeypatch):
    app = FastAPI()
    app.include_router(clinical_cases.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=UserRole.SUPERUSER)
    db = Mock()
    db.get.side_effect = [
        SimpleNamespace(active=True, case_type=CaseType.DEFAULT),
        SimpleNamespace(namespace_key="friendly_polite"),
    ]
    app.dependency_overrides[get_db] = lambda: db
    closed = Mock()

    def stream(request):
        assert request.text == "Hola"
        assert request.vocal_style.profile_key == "friendly_polite"
        try:
            yield b"first"
            yield b"second"
        finally:
            closed()

    monkeypatch.setattr(speech, "AzureOpenAITextToSpeechProvider", lambda: SimpleNamespace(stream=stream))
    with TestClient(app) as client:
        response = client.post("/clinical-cases/5/patient-preview/speech?progressive=true", json={
            "text": "Hola", "gender": "female", "personality_id": 1,
        })
    assert response.status_code == 200
    assert response.content == b"firstsecond"
    assert response.headers["x-accel-buffering"] == "no"
    closed.assert_called_once()
    db.commit.assert_not_called()
