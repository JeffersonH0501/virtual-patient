"""Async client for the internal video-processing worker service."""

from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel

from app.core.config import settings


class VideoProcessingWorkerError(RuntimeError):
    """Raised when the internal visual service cannot complete a request."""


async def warmup_video_processing_worker() -> None:
    """Ask the single visual service to load its models for calibration."""
    headers = {"X-Video-Worker-Token": settings.video_processing_worker_token}
    timeout = httpx.Timeout(settings.video_processing_worker_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.video_processing_worker_url}/internal/warmup",
                headers=headers,
            )
    except httpx.HTTPError as error:
        raise VideoProcessingWorkerError(
            "The video-processing worker is unavailable"
        ) from error
    if response.status_code != 200:
        raise VideoProcessingWorkerError(
            f"The video-processing worker returned HTTP {response.status_code}"
        )


async def process_calibration_video(
    path: Path,
    metadata: BaseModel,
    mode: str,
) -> dict:
    """Send a temporary calibration clip to the single visual worker."""
    if mode not in {"video", "gaze", "camera"}:
        raise ValueError(f"Unsupported visual calibration mode: {mode}")

    headers = {"X-Video-Worker-Token": settings.video_processing_worker_token}
    timeout = httpx.Timeout(settings.video_processing_worker_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            with path.open("rb") as media:
                response = await client.post(
                    f"{settings.video_processing_worker_url}/internal/calibration/{mode}",
                    headers=headers,
                    data={"metadata_json": metadata.model_dump_json()},
                    files={"media": (path.name, media, "application/octet-stream")},
                )
    except (OSError, httpx.HTTPError) as error:
        raise VideoProcessingWorkerError(
            "The video-processing worker is unavailable"
        ) from error

    if response.status_code != 200:
        raise VideoProcessingWorkerError(
            f"The video-processing worker returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise VideoProcessingWorkerError(
            "The video-processing worker returned invalid JSON"
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise VideoProcessingWorkerError(
            "The video-processing worker returned an invalid result"
        )
    return payload["result"]
