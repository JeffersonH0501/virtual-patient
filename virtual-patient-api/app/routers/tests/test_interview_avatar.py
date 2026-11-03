"""Tests for the Tavus avatar client and session lifecycle."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi import HTTPException

from app.avatar import AvatarConfigurationError, AvatarProviderError, TavusClient
from app.routers import interview_avatar


def _settings(**overrides):
    values = {
        "tavus_api_key": "secret-key",
        "tavus_pal_id": "pal123",
        "tavus_face_id": None,
        "tavus_male_face_id": "male-face",
        "tavus_female_face_id": "female-face",
        "tavus_api_base_url": "https://tavus.test",
        "tavus_max_call_duration_seconds": 900,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _response(status_code=200, payload=None):
    request = httpx.Request("POST", "https://tavus.test")
    return httpx.Response(status_code, json=payload or {}, request=request)


class TavusClientTests(unittest.TestCase):
    def test_requires_key_and_pal(self):
        self.assertFalse(TavusClient(_settings(tavus_api_key=None)).configured)
        self.assertFalse(TavusClient(_settings(tavus_pal_id=None)).configured)
        self.assertTrue(TavusClient(_settings()).configured)

    def test_unconfigured_client_does_not_call_provider(self):
        client = TavusClient(_settings(tavus_api_key=None))
        with patch("app.avatar.tavus.httpx.post") as post:
            with self.assertRaises(AvatarConfigurationError):
                client.create_session(7)
        post.assert_not_called()

    def test_creates_private_conversation_with_server_side_key(self):
        payload = {
            "conversation_id": "c1",
            "conversation_url": "https://tavus.daily.co/c1",
            "meeting_token": "token",
        }
        with patch(
            "app.avatar.tavus.httpx.post", return_value=_response(payload=payload)
        ) as post:
            session = TavusClient(_settings(tavus_face_id="face1")).create_session(7)

        self.assertEqual(session.conversation_id, "c1")
        self.assertEqual(session.meeting_token, "token")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-api-key"], "secret-key")
        self.assertTrue(kwargs["json"]["require_auth"])
        self.assertEqual(kwargs["json"]["pal_id"], "pal123")
        self.assertEqual(kwargs["json"]["face_id"], "face1")
        self.assertEqual(kwargs["json"]["properties"]["max_call_duration"], 900)

    def test_conversation_uses_patient_language_and_gender_face(self):
        payload = {
            "conversation_id": "c1",
            "conversation_url": "https://tavus.daily.co/c1",
        }
        with patch(
            "app.avatar.tavus.httpx.post", return_value=_response(payload=payload)
        ) as post:
            TavusClient(_settings()).create_session(7, gender="female", language="es")

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["face_id"], "female-face")
        self.assertEqual(body["properties"]["languages"], ["es"])

    def test_face_map_selects_face_by_gender_age_and_personality(self):
        payload = {
            "conversation_id": "c1",
            "conversation_url": "https://tavus.daily.co/c1",
        }
        face_map = '{"female:senior": "old-f", "female:senior:anxious": "old-f-anx"}'
        with patch(
            "app.avatar.tavus.httpx.post", return_value=_response(payload=payload)
        ) as post:
            client = TavusClient(_settings(tavus_face_map=face_map))
            client.create_session(7, gender="female", age=70, personality_key="anxious")
            self.assertEqual(post.call_args.kwargs["json"]["face_id"], "old-f-anx")
            client.create_session(7, gender="female", age=70, personality_key="calm")
            self.assertEqual(post.call_args.kwargs["json"]["face_id"], "old-f")
            client.create_session(7, gender="female", age=30)
            self.assertEqual(post.call_args.kwargs["json"]["face_id"], "female-face")

    def test_provider_failure_is_wrapped(self):
        with patch(
            "app.avatar.tavus.httpx.post", return_value=_response(status_code=500)
        ):
            with self.assertRaises(AvatarProviderError):
                TavusClient(_settings()).create_session(7)

    def test_incomplete_provider_payload_is_rejected(self):
        with patch(
            "app.avatar.tavus.httpx.post",
            return_value=_response(payload={"conversation_id": "c1"}),
        ):
            with self.assertRaises(AvatarProviderError):
                TavusClient(_settings()).create_session(7)

    def test_ending_an_already_closed_conversation_is_not_an_error(self):
        with patch(
            "app.avatar.tavus.httpx.post", return_value=_response(status_code=404)
        ):
            TavusClient(_settings()).end_session("c1")


class _Query:
    def __init__(self, interview):
        self.interview = interview

    def filter(self, *args):
        del args
        return self

    def first(self):
        return self.interview


class _Database:
    def __init__(self, interview):
        self.interview = interview

    def query(self, entity):
        del entity
        return _Query(self.interview)


class AvatarSessionRouteTests(unittest.TestCase):
    def setUp(self):
        interview_avatar._active_conversations.clear()
        self.user = SimpleNamespace(id=1)
        self.client = MagicMock()
        self.client.configured = True
        self.client.create_session.return_value = SimpleNamespace(
            conversation_id="c1",
            conversation_url="https://tavus.daily.co/c1",
            meeting_token="token",
        )

    def _start(self, interview):
        return interview_avatar.start_avatar_session(
            7, client=self.client, db=_Database(interview), current_user=self.user
        )

    def test_unknown_or_foreign_interview_is_not_found(self):
        with self.assertRaises(HTTPException) as raised:
            self._start(None)
        self.assertEqual(raised.exception.status_code, 404)

    def test_only_in_progress_interviews_can_start_a_session(self):
        with self.assertRaises(HTTPException) as raised:
            self._start(SimpleNamespace(status="completed"))
        self.assertEqual(raised.exception.status_code, 409)
        self.client.create_session.assert_not_called()

    def test_unconfigured_provider_returns_service_unavailable(self):
        self.client.configured = False
        with self.assertRaises(HTTPException) as raised:
            self._start(SimpleNamespace(status="in_progress"))
        self.assertEqual(raised.exception.status_code, 503)

    def test_provider_failure_returns_bad_gateway(self):
        self.client.create_session.side_effect = AvatarProviderError("down")
        with self.assertRaises(HTTPException) as raised:
            self._start(SimpleNamespace(status="in_progress"))
        self.assertEqual(raised.exception.status_code, 502)

    def test_starts_and_ends_only_the_session_created_for_the_interview(self):
        interview = SimpleNamespace(
            status="in_progress",
            interview_metadata={"patient_response_language": "es"},
            personality=SimpleNamespace(namespace_key="friendly_polite"),
            patient_gender="female",
            clinical_case=SimpleNamespace(age=70),
        )
        response = self._start(interview)
        self.assertEqual(response.conversation_id, "c1")
        self.assertEqual(response.state, "created")
        self.assertEqual(response.patient_profile.language, "es")
        self.assertEqual(
            response.patient_profile.personality_key,
            "friendly_polite",
        )
        self.client.create_session.assert_called_once_with(
            7,
            gender="female",
            language="es",
            age=70,
            personality_key="friendly_polite",
        )

        interview_avatar.end_avatar_session(
            7,
            client=self.client,
            db=_Database(SimpleNamespace(status="in_progress")),
            current_user=self.user,
        )
        self.client.end_session.assert_called_once_with("c1")
        self.assertNotIn(7, interview_avatar._active_conversations)

    def test_restart_ends_the_previous_session(self):
        self._start(SimpleNamespace(status="in_progress"))
        self._start(SimpleNamespace(status="in_progress"))
        self.client.end_session.assert_called_once_with("c1")


if __name__ == "__main__":
    unittest.main()
