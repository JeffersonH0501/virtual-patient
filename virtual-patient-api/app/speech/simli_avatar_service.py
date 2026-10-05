"""Simli AI Avatar orchestration service (AvatarRenderService wrapper).

Integrates with the Simli Audio-to-Video API according to Section 7.2 of the
Virtual Patient technical evaluation report.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional
import requests

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class SimliConfigurationError(RuntimeError):
    """Raised when the Simli integration is misconfigured or disabled."""


class SimliProviderError(RuntimeError):
    """Raised when communication with the upstream Simli API fails."""


@dataclass(frozen=True)
class SimliSessionConfig:
    session_token: str
    ice_servers: List[Dict[str, Any]]
    face_id: str
    max_session_length: int
    max_idle_time: int


class SimliAvatarService:
    """Wrapper for the Simli Audio-to-Video WebRTC API."""

    def __init__(
        self,
        configuration: Settings = settings,
        session_requester: Any = None,
    ):
        self.configuration = configuration
        self._session_requester = session_requester or requests

    @property
    def is_enabled(self) -> bool:
        """Check if Simli integration is enabled and has an API key configured."""
        return bool(
            self.configuration.simli_avatar_enabled
            and self.configuration.simli_api_key
        )

    def resolve_face_id(
        self,
        gender: Optional[str] = None,
        character_override: Optional[str] = None,
    ) -> str:
        """Determine the face ID to use based on gender and overrides."""
        if character_override and character_override.strip():
            return character_override.strip()

        normalized_gender = (gender or "").strip().lower()
        if normalized_gender in ("female", "f", "mujer", "femenino"):
            if self.configuration.simli_default_face_id_female:
                return self.configuration.simli_default_face_id_female

        if self.configuration.simli_default_face_id_male:
            return self.configuration.simli_default_face_id_male

        if self.configuration.simli_default_face_id_female:
            return self.configuration.simli_default_face_id_female

        # Fallback placeholder if no face ID is yet provisioned in environment
        return "default-patient-face"

    def get_session_configuration(
        self,
        gender: Optional[str] = None,
        character_override: Optional[str] = None,
    ) -> SimliSessionConfig:
        """Negotiate ephemeral session credentials with Simli API."""
        if not self.configuration.simli_avatar_enabled:
            raise SimliConfigurationError("Simli avatar integration is disabled.")

        api_key = self.configuration.simli_api_key
        if not api_key:
            raise SimliConfigurationError("SIMLI_API_KEY is not configured.")

        face_id = self.resolve_face_id(gender, character_override)
        base_url = self.configuration.simli_api_url.rstrip("/")

        headers = {
            "Content-Type": "application/json",
            "x-simli-api-key": api_key,
        }

        # 1. Request session token
        token_payload = {
            "faceId": face_id,
            "handleSilence": True,
            "maxSessionLength": self.configuration.simli_max_session_length,
            "maxIdleTime": self.configuration.simli_max_idle_time,
            "model": "fasttalk",
        }

        try:
            token_response = self._session_requester.post(
                f"{base_url}/compose/token",
                json=token_payload,
                headers=headers,
                timeout=10,
            )
        except Exception as exc:
            logger.error("Failed to connect to Simli token endpoint: %s", exc)
            raise SimliProviderError(f"Simli connection error: {exc}") from exc

        if not token_response.ok:
            logger.error(
                "Simli token request failed [%s]: %s",
                token_response.status_code,
                token_response.text,
            )
            raise SimliProviderError(
                f"Simli returned error status {token_response.status_code}: {token_response.text}"
            )

        try:
            token_data = token_response.json()
            session_token = token_data.get("session_token")
            if not session_token:
                raise ValueError("Response missing 'session_token'")
        except Exception as exc:
            logger.error("Invalid token response from Simli: %s", exc)
            raise SimliProviderError("Invalid response from Simli API") from exc

        # 2. Request ICE servers (STUN/TURN)
        ice_servers: List[Dict[str, Any]] = []
        try:
            ice_response = self._session_requester.get(
                f"{base_url}/compose/ice",
                headers=headers,
                timeout=10,
            )
            if ice_response.ok:
                ice_data = ice_response.json()
                if isinstance(ice_data, list):
                    ice_servers = ice_data
                elif isinstance(ice_data, dict) and "ice_servers" in ice_data:
                    ice_servers = ice_data["ice_servers"]
        except Exception as exc:
            logger.warning("Could not fetch Simli ICE servers: %s. Proceeding with defaults.", exc)

        return SimliSessionConfig(
            session_token=session_token,
            ice_servers=ice_servers,
            face_id=face_id,
            max_session_length=self.configuration.simli_max_session_length,
            max_idle_time=self.configuration.simli_max_idle_time,
        )

