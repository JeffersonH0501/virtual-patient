"""Private, provider-neutral storage for interview media."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from fastapi import HTTPException, UploadFile


# Interview media storage settings. Hardcoded on purpose: the storage root is the
# in-container mount point (backed by a Docker volume), and the minimum free space
# guard is fixed for the deployment. Neither is sourced from the environment.
MEDIA_STORAGE_ROOT = Path("/app/media")
MEDIA_MIN_FREE_BYTES = 256 * 1024 * 1024  # 256 MiB
MIB = 1024 * 1024
TURN_VIDEO_MAX_BYTES = 64 * MIB
RECORDING_FILE_LIMITS = {
    "student_audio": 64 * MIB,
    "patient_audio": 64 * MIB,
    "student_video": 512 * MIB,
    "patient_video": 512 * MIB,
}


def check_upload_size(size: int, limit: int) -> None:
    if size > limit:
        raise HTTPException(status_code=413, detail="Interview media exceeds the maximum allowed size")


async def checked_upload_chunks(upload: UploadFile, limit: int) -> AsyncIterator[bytes]:
    check_upload_size(upload.size or 0, limit)
    size = 0
    while chunk := await upload.read(MIB):
        size += len(chunk)
        check_upload_size(size, limit)
        yield chunk


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
        relative_dir = Path("interviews") / str(interview_id) / recording_id
        filename = f"{kind}-{uuid.uuid4().hex}{extension}"
        return await self._save_upload(relative_dir / filename, upload, RECORDING_FILE_LIMITS[kind])

    async def save_turn_video_upload(
        self, interview_id: int, recording_id: str, turn_id: str, upload: UploadFile, extension: str
    ) -> StoredMedia:
        """Atomically store a temporary video segment for one conversation turn."""
        relative_dir = Path("interviews") / str(interview_id) / recording_id / "turns"
        filename = f"{turn_id}-{uuid.uuid4().hex}{extension}"
        return await self._save_upload(relative_dir / filename, upload, TURN_VIDEO_MAX_BYTES)

    async def _save_upload(self, relative_path: Path, upload: UploadFile, limit: int) -> StoredMedia:
        target = (self.root / relative_path).resolve()
        self._assert_within_root(target)
        temporary = target.with_name(f".{target.name}.tmp")
        digest = hashlib.sha256()
        size = 0
        try:
            try:
                self._ensure_free_space()
                target.parent.mkdir(parents=True, exist_ok=True)
                with temporary.open("xb") as output:
                    async for chunk in checked_upload_chunks(upload, limit):
                        self._ensure_free_space(len(chunk))
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                await upload.close()
            # Publish after the last await so cancellation cannot orphan the result.
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredMedia(relative_path.as_posix(), size, digest.hexdigest())

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

    def _ensure_free_space(self, incoming_bytes: int = 0) -> None:
        available = shutil.disk_usage(self.root).free
        if available - incoming_bytes < MEDIA_MIN_FREE_BYTES:
            raise OSError("Insufficient free space for interview media")


_storage: LocalMediaStorage | None = None


def get_media_storage() -> LocalMediaStorage:
    global _storage
    if _storage is None:
        _storage = LocalMediaStorage(MEDIA_STORAGE_ROOT)
    return _storage
