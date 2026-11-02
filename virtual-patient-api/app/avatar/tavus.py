"""Server-side Tavus Conversational Video Interface client.

The API key never leaves the backend. The browser only receives the private
room URL and a meeting token scoped to one conversation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import Settings, settings as default_settings


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15.0
PARTICIPANT_ABSENT_TIMEOUT_SECONDS = 120
PARTICIPANT_LEFT_TIMEOUT_SECONDS = 30


class AvatarConfigurationError(RuntimeError):
    """Raised when the avatar provider is not configured."""


class AvatarProviderError(RuntimeError):
    """Raised when the avatar provider rejects or fails a request."""


@dataclass(frozen=True)
class AvatarSession:
    """Credentials needed by the browser to join one avatar conversation."""

    conversation_id: str
    conversation_url: str
    meeting_token: str | None


class TavusClient:
    """Create and end private Tavus conversations."""

    def __init__(self, config: Settings = default_settings) -> None:
        self._config = config

    @property
    def configured(self) -> bool:
        return bool(self._config.tavus_api_key and self._config.tavus_pal_id)

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise AvatarConfigurationError("Tavus is not configured")
        return {
            "x-api-key": str(self._config.tavus_api_key),
            "Content-Type": "application/json",
        }

    def create_session(self, interview_id: int) -> AvatarSession:
        headers = self._headers()
        body: dict[str, object] = {
            "pal_id": self._config.tavus_pal_id,
            "conversation_name": f"virtual-patient-interview-{interview_id}",
            "require_auth": True,
            "properties": {
                "max_call_duration": self._config.tavus_max_call_duration_seconds,
                "participant_absent_timeout": PARTICIPANT_ABSENT_TIMEOUT_SECONDS,
                "participant_left_timeout": PARTICIPANT_LEFT_TIMEOUT_SECONDS,
            },
        }
        if self._config.tavus_face_id:
            body["face_id"] = self._config.tavus_face_id
        try:
            response = httpx.post(
                f"{self._config.tavus_api_base_url}/v2/conversations",
                headers=headers,
                json=body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(
                "tavus_create_failed interview_id=%s error=%s",
                interview_id,
                type(error).__name__,
            )
            raise AvatarProviderError("Tavus could not create the conversation") from error

        conversation_id = payload.get("conversation_id")
        conversation_url = payload.get("conversation_url")
        if not conversation_id or not conversation_url:
            raise AvatarProviderError("Tavus returned an incomplete conversation")
        return AvatarSession(
            conversation_id=str(conversation_id),
            conversation_url=str(conversation_url),
            meeting_token=payload.get("meeting_token"),
        )

    def end_session(self, conversation_id: str) -> None:
        headers = self._headers()
        try:
            response = httpx.post(
                f"{self._config.tavus_api_base_url}/v2/conversations/{conversation_id}/end",
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            # An already ended conversation is not an error for the caller.
            if response.status_code not in (404, 409):
                response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning(
                "tavus_end_failed conversation_id=%s error=%s",
                conversation_id,
                type(error).__name__,
            )
            raise AvatarProviderError("Tavus could not end the conversation") from error
