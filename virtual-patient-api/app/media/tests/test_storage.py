"""Unit tests for private interview media storage."""

from io import BytesIO
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.media.storage import LocalMediaStorage


class LocalMediaStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_upload_leaves_no_file(self) -> None:
        for error in (asyncio.CancelledError(), HTTPException(status_code=413)):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                storage = LocalMediaStorage(Path(directory))
                upload = UploadFile(file=BytesIO(), filename="capture.webm")
                if isinstance(error, HTTPException):
                    read = AsyncMock(side_effect=[b"1234", b"5678"])
                else:
                    read = AsyncMock(side_effect=[b"1234", error])
                with patch.object(upload, "read", read), patch("app.media.storage.TURN_VIDEO_MAX_BYTES", 5):
                    with self.assertRaises(type(error)) as raised:
                        await storage.save_turn_video_upload(14, "recording", "turn", upload, ".webm")
                if isinstance(error, HTTPException):
                    self.assertEqual(raised.exception.status_code, 413)
                self.assertTrue(upload.file.closed)
                self.assertFalse(any(path.is_file() for path in storage.root.rglob("*")))

    async def test_upload_is_saved_atomically_with_checksum(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage = LocalMediaStorage(Path(temporary_directory))
            upload = UploadFile(
                file=BytesIO(b"synchronized-media"),
                filename="capture.webm",
                headers=Headers({"content-type": "video/webm"}),
            )

            stored = await storage.save_upload(
                interview_id=14,
                recording_id="recording-id",
                kind="student_video",
                upload=upload,
                extension=".webm",
            )

            path = storage.resolve(stored.storage_key)
            self.assertEqual(path.read_bytes(), b"synchronized-media")
            self.assertEqual(stored.size_bytes, len(b"synchronized-media"))
            self.assertEqual(
                stored.sha256,
                "aefcf47c3182b52bc9bf4809c91644d517988e38bd012f1b35a57e67a119fd54",
            )
            self.assertFalse(any(path.parent.glob("*.tmp")))

    async def test_storage_key_cannot_escape_private_root(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            storage = LocalMediaStorage(Path(temporary_directory))

            with self.assertRaises(ValueError):
                storage.resolve("../../outside.webm")

    async def test_range_iterator_returns_only_requested_bytes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "media.webm"
            path.write_bytes(b"0123456789")
            storage = LocalMediaStorage(Path(temporary_directory))

            chunks = [chunk async for chunk in storage.iter_range(path, 2, 5, 2)]

            self.assertEqual(b"".join(chunks), b"2345")

    async def test_delete_interview_removes_all_recordings_for_only_that_interview(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "interviews" / "23" / "recording-a"
            retained = root / "interviews" / "24" / "recording-b"
            target.mkdir(parents=True)
            retained.mkdir(parents=True)
            (target / "student_video.webm").write_bytes(b"video")
            (retained / "student_audio.webm").write_bytes(b"audio")
            storage = LocalMediaStorage(root)

            storage.delete_interview(23)

            self.assertFalse((root / "interviews" / "23").exists())
            self.assertTrue((retained / "student_audio.webm").is_file())
