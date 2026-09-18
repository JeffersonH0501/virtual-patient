"""Private, provider-neutral storage for interview media."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from fastapi import UploadFile


# Interview media storage settings. Hardcoded on purpose: the storage root is the
# in-container mount point (backed by a Docker volume), and the minimum free space
# guard is fixed for the deployment. Neither is sourced from the environment.
MEDIA_STORAGE_ROOT = Path("/app/media")
MEDIA_MIN_FREE_BYTES = 256 * 1024 * 1024  # 256 MiB


@dataclass(frozen=True)
class StoredMedia:
    storage_key: str
    size_bytes: int
    sha256: str


class LocalMediaStorage:
    """Store private media below one configured filesystem root."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        interview_id: int,
        recording_id: str,
        kind: str,
        upload: UploadFile,
        extension: str,
    ) -> StoredMedia:
        self._ensure_free_space()
        relative_dir = Path("interviews") / str(interview_id) / recording_id
        target_dir = (self.root / relative_dir).resolve()
        self._assert_within_root(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{kind}{extension}"
        target = target_dir / filename
        temporary = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        storage_key = (relative_dir / filename).as_posix()
        return StoredMedia(storage_key=storage_key, size_bytes=size, sha256=digest.hexdigest())

    async def save_calibration_upload(
        self, user_id: int, attempt_id: str, kind: str, upload: UploadFile, extension: str
    ) -> StoredMedia:
        """Persist an immutable calibration source below its own lifecycle path."""
        self._ensure_free_space()
        relative_dir = Path("calibrations") / str(user_id) / attempt_id
        target_dir = (self.root / relative_dir).resolve()
        self._assert_within_root(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{kind}{extension}"
        target = target_dir / filename
        temporary = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return StoredMedia((relative_dir / filename).as_posix(), size, digest.hexdigest())

    async def save_turn_video_upload(
        self, interview_id: int, recording_id: str, turn_id: str, upload: UploadFile, extension: str
    ) -> StoredMedia:
        """Atomically store a temporary video segment for one conversation turn."""
        self._ensure_free_space()
        relative_dir = Path("interviews") / str(interview_id) / recording_id / "turns"
        target_dir = (self.root / relative_dir).resolve()
        self._assert_within_root(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{turn_id}-{uuid.uuid4().hex}{extension}"
        target = target_dir / filename
        temporary = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return StoredMedia((relative_dir / filename).as_posix(), size, digest.hexdigest())

    def resolve(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        self._assert_within_root(path)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def delete(self, storage_key: str) -> None:
        path = (self.root / storage_key).resolve()
        self._assert_within_root(path)
        path.unlink(missing_ok=True)

    def delete_recording(self, interview_id: int, recording_id: str) -> None:
        directory = (self.root / "interviews" / str(interview_id) / recording_id).resolve()
        self._assert_within_root(directory)
        if directory.is_dir():
            shutil.rmtree(directory)

    def delete_interview(self, interview_id: int) -> None:
        directory = (self.root / "interviews" / str(interview_id)).resolve()
        self._assert_within_root(directory)
        if directory.is_dir():
            shutil.rmtree(directory)

    async def iter_range(
        self,
        path: Path,
        start: int,
        end: int,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        remaining = end - start + 1
        with path.open("rb") as media_file:
            media_file.seek(start)
            while remaining > 0:
                chunk = media_file.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def _assert_within_root(self, path: Path) -> None:
        if path != self.root and self.root not in path.parents:
            raise ValueError("Media path escapes the configured storage root")

    def _ensure_free_space(self) -> None:
        available = shutil.disk_usage(self.root).free
        if available < MEDIA_MIN_FREE_BYTES:
            raise OSError("Insufficient free space for interview media")


_storage: LocalMediaStorage | None = None


def get_media_storage() -> LocalMediaStorage:
    global _storage
    if _storage is None:
        _storage = LocalMediaStorage(MEDIA_STORAGE_ROOT)
    return _storage
