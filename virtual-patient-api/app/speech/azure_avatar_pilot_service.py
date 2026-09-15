"""Azure AI Speech Avatar Pilot Service with telemetry collection and session management."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings
from app.speech.avatar_ssml import (
    render_avatar_ssml,
    select_avatar_character,
    select_avatar_style,
    select_avatar_voice,
)
from app.speech.vocal_style_policy import select_patient_vocal_style

logger = logging.getLogger(__name__)

# Standard Azure Speech Avatar pricing for calculations ($0.56 / minute active)
AZURE_AVATAR_COST_PER_SECOND = 0.56 / 60.0


@dataclass
class TurnTelemetry:
    turn_index: int
    timestamp: str
    ttff_ms: float
    rtt_ms: float
    jitter_ms: float
    packet_loss_pct: float
    frame_rate: float
    resolution: str
    active_duration_seconds: float
    estimated_cost_usd: float


class AzureAvatarPilotService:
    """Manages Azure AI Speech Avatar sessions and empirical telemetry collection."""

    def __init__(self):
        self.api_key = settings.azure_speech_key
        self.region = settings.azure_speech_region
        self.telemetry_dir = Path(settings.avatar_pilot_telemetry_dir)
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_configured(self) -> bool:
        return bool(settings.avatar_pilot_enabled and self.api_key and self.region)

    def get_client_configuration(
        self,
        gender: Optional[str] = None,
        character_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue temporary Azure Speech and relay credentials for the browser SDK."""
        character = character_override or select_avatar_character(gender)
        voice = select_avatar_voice(gender)

        if not self.is_configured:
            raise RuntimeError(
                "Azure Avatar is disabled or Azure Speech credentials are not configured."
            )

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
        }

        try:
            speech_token_response = requests.post(
                f"https://{self.region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
                headers=headers,
                timeout=10,
            )
            speech_token_response.raise_for_status()
            speech_token = speech_token_response.text.strip()
            if not speech_token:
                raise RuntimeError("Azure Speech returned an empty authorization token.")

            relay_response = requests.get(
                f"https://{self.region}.tts.speech.microsoft.com/"
                "cognitiveservices/avatar/relay/token/v1",
                headers=headers,
                timeout=10,
            )
            relay_response.raise_for_status()
            relay = relay_response.json()
            urls = relay.get("urls") or relay.get("Urls")
            username = relay.get("username") or relay.get("Username")
            credential = relay.get("password") or relay.get("Password")
            if not urls or not username or not credential:
                raise RuntimeError("Azure Speech returned incomplete relay credentials.")

            return {
                "speech_token": speech_token,
                "ice_servers": [{"urls": urls, "username": username, "credential": credential}],
                "character": character,
                "voice": voice,
                "style": select_avatar_style(gender),
                "region": self.region,
            }
        except Exception as error:
            logger.error("Failed to obtain Azure Avatar client configuration: %s", error)
            raise RuntimeError(f"Azure Avatar initialization failed: {error}") from error

    def save_turn_telemetry(self, interview_id: int, turn_data: Dict[str, Any]) -> None:
        """Persist client-side turn metrics to disk for empirical validation (Section 4.4)."""
        file_path = self.telemetry_dir / f"interview_{interview_id}.json"
        existing_turns: List[Dict[str, Any]] = []

        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        existing_turns = content
            except Exception as error:
                logger.warning("Could not read existing telemetry file: %s", error)

        turn_index = len(existing_turns) + 1
        active_duration = float(turn_data.get("active_duration_seconds", 0.0))
        estimated_cost = active_duration * AZURE_AVATAR_COST_PER_SECOND

        telemetry_entry = TurnTelemetry(
            turn_index=turn_index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            ttff_ms=float(turn_data.get("ttff_ms", 0.0)),
            rtt_ms=float(turn_data.get("rtt_ms", 0.0)),
            jitter_ms=float(turn_data.get("jitter_ms", 0.0)),
            packet_loss_pct=float(turn_data.get("packet_loss_pct", 0.0)),
            frame_rate=float(turn_data.get("frame_rate", 30.0)),
            resolution=str(turn_data.get("resolution", "1280x720")),
            active_duration_seconds=active_duration,
            estimated_cost_usd=round(estimated_cost, 4),
        )

        existing_turns.append(asdict(telemetry_entry))

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing_turns, f, indent=2)

    def get_telemetry_summary(self, interview_id: int) -> Dict[str, Any]:
        """Aggregate empirical benchmark metrics for Section 4.4 reporting."""
        file_path = self.telemetry_dir / f"interview_{interview_id}.json"
        if not file_path.exists():
            return {
                "interview_id": interview_id,
                "total_turns": 0,
                "message": "No telemetry recorded yet for this interview.",
            }

        with open(file_path, "r", encoding="utf-8") as f:
            turns: List[Dict[str, Any]] = json.load(f)

        if not turns:
            return {"interview_id": interview_id, "total_turns": 0}

        ttff_values = sorted(t["ttff_ms"] for t in turns if t.get("ttff_ms") is not None)
        rtt_values = [t["rtt_ms"] for t in turns if t.get("rtt_ms") is not None]
        jitter_values = [t["jitter_ms"] for t in turns if t.get("jitter_ms") is not None]
        packet_loss_values = [t["packet_loss_pct"] for t in turns if t.get("packet_loss_pct") is not None]
        total_active_seconds = sum(t["active_duration_seconds"] for t in turns)
        total_cost_usd = sum(t["estimated_cost_usd"] for t in turns)

        def percentile(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            k = (len(values) - 1) * p
            f = int(k)
            c = min(f + 1, len(values) - 1)
            d = k - f
            return values[f] + d * (values[c] - values[f])

        p50_ttff = percentile(ttff_values, 0.50)
        p95_ttff = percentile(ttff_values, 0.95)
        mean_ttff = sum(ttff_values) / len(ttff_values) if ttff_values else 0.0
        mean_rtt = sum(rtt_values) / len(rtt_values) if rtt_values else 0.0
        mean_jitter = sum(jitter_values) / len(jitter_values) if jitter_values else 0.0
        mean_packet_loss = sum(packet_loss_values) / len(packet_loss_values) if packet_loss_values else 0.0

        # Protocol compliance assessment against Section 4.4 criteria
        compliance = {
            "step_1_webrtc_latency": {
                "target_rtt_ms": "< 250",
                "measured_rtt_ms": round(mean_rtt, 1),
                "passed": mean_rtt < 250,
            },
            "step_2_ttff": {
                "target_ttff_ms": "< 1500",
                "measured_p95_ttff_ms": round(p95_ttff, 1),
                "passed": p95_ttff < 1500,
            },
            "step_6_cost_audit": {
                "target_cost_per_15min_session_usd": "<= 3.90",
                "projected_15min_cost_usd": round(
                    (total_cost_usd / max(total_active_seconds, 1)) * (15 * 60 * 0.45), 2
                ),
                "idle_optimization_active": settings.azure_speech_avatar_idle_optimization,
            },
        }

        return {
            "interview_id": interview_id,
            "total_turns": len(turns),
            "latency_metrics": {
                "p50_ttff_ms": round(p50_ttff, 1),
                "p95_ttff_ms": round(p95_ttff, 1),
                "mean_ttff_ms": round(mean_ttff, 1),
                "mean_rtt_ms": round(mean_rtt, 1),
                "mean_jitter_ms": round(mean_jitter, 1),
                "mean_packet_loss_pct": round(mean_packet_loss, 2),
            },
            "cost_metrics": {
                "total_active_streaming_seconds": round(total_active_seconds, 1),
                "estimated_cost_usd": round(total_cost_usd, 4),
            },
            "protocol_compliance": compliance,
            "raw_turns": turns,
        }

