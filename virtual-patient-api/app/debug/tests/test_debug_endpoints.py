"""Focused tests for the DEV/DEBUG-ONLY multimodal calibration debug endpoints.

Scope
-----
These tests exercise the two debug router coroutines
(``debug_pyfeat_frame`` / ``debug_opensmile_audio``), the upload guards in
``_read_capped``, and the debug response schemas. They deliberately do NOT run
the real extractors: Py-Feat, OpenCV, and OpenSMILE are heavy, optional
dependencies that are not part of the unit-test environment, so
``detect_frame`` / ``process_audio_chunk`` are monkeypatched. Only the router's
own behaviour (guards, schema pass-through, and the extractor-unavailable ->
503 mapping) plus the schema defaults are covered here. The real extractor
execution paths are intentionally out of scope for a unit test.

Import strategy
---------------
Importing ``app.routers.debug`` the normal way runs ``app/routers/__init__.py``,
which eagerly imports the full LLM/agent chain (``langchain_openai`` et al.)
that is not installed in the unit-test environment. The debug router itself only
depends on cleanly-importable modules (auth, user model, debug helpers) plus
FastAPI ``File``/``Form`` (``python-multipart``). We therefore load
``app/routers/debug.py`` directly from its file path, bypassing the heavy
package ``__init__``. In a fully-provisioned environment the plain import works
too, so we try that first and fall back to the file-path loader.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import pathlib
import unittest

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from app.core.auth import get_current_active_user
from app.debug.opensmile_debug import OpenSmileDebugUnavailable
from app.debug.openface_debug import OpenFaceDebugUnavailable
from app.debug.schemas import (
    DebugUnavailable,
    ExtractorInfo,
    OpenSmileFrameDebug,
    PyFeatFrameDebug,
)


def _load_debug_router():
    """Return the debug router module without triggering the LLM import chain.

    Prefers the normal package import; falls back to a direct file-path load of
    ``app/routers/debug.py`` when the heavy ``app.routers`` package ``__init__``
    cannot be imported (missing optional agent dependencies).
    """
    try:  # pragma: no cover - taken only in a fully-provisioned environment
        import app.routers.debug as module

        return module
    except Exception:  # noqa: BLE001 - any failure means we use the direct loader
        path = pathlib.Path(__file__).resolve().parents[2] / "routers" / "debug.py"
        spec = importlib.util.spec_from_file_location("app.routers.debug", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


debug_router = _load_debug_router()


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeUpload:
    """Minimal ``UploadFile`` stand-in for the debug endpoints.

    Exposes only what ``_read_capped`` and the endpoints touch: a
    ``content_type`` attribute and an awaitable ``read()`` returning preset
    bytes. This avoids a multipart HTTP request while still driving the guard
    and read path.
    """

    def __init__(self, *, content_type: str | None, data: bytes):
        self.content_type = content_type
        self._data = data

    async def read(self) -> bytes:
        return self._data


def _current_user():
    """A stub current user; the endpoints never read its attributes."""
    return object()


def _run(coro):
    return asyncio.run(coro)


def _valid_pyfeat() -> PyFeatFrameDebug:
    return PyFeatFrameDebug(
        face_detected=True,
        face_score=0.99,
        gaze_yaw=1.0,
        landmarks=[[10.0, 20.0], [30.0, 40.0]],
        image_width=640,
        image_height=480,
        extractor=ExtractorInfo(name="openface", version="3.0", detector="openface3-multitask"),
    )


def _valid_opensmile() -> OpenSmileFrameDebug:
    return OpenSmileFrameDebug(
        f0_semitones=12.3,
        loudness=0.4,
        voicing=0.8,
        voicing_kind="hnr_dbacf",
        frame_timestamp_ms=1234.0,
    )


# ---------------------------------------------------------------------------
# Auth: the endpoints are authenticated
# ---------------------------------------------------------------------------


class DebugEndpointAuthTests(unittest.TestCase):
    def test_frame_endpoint_requires_current_user_via_dependency(self):
        # The signature declares current_user defaulting to
        # Depends(get_current_active_user); that documents the auth requirement.
        signature = inspect.signature(debug_router.debug_openface_frame)
        self.assertIn("current_user", signature.parameters)
        dependency = signature.parameters["current_user"].default
        self.assertEqual(getattr(dependency, "dependency", None), get_current_active_user)

    def test_audio_endpoint_requires_current_user_via_dependency(self):
        signature = inspect.signature(debug_router.debug_opensmile_audio)
        self.assertIn("current_user", signature.parameters)
        dependency = signature.parameters["current_user"].default
        self.assertEqual(getattr(dependency, "dependency", None), get_current_active_user)


# ---------------------------------------------------------------------------
# Schema pass-through: a valid extractor result is returned unchanged
# ---------------------------------------------------------------------------


class DebugFramePassThroughTests(unittest.TestCase):
    def test_returns_valid_pyfeat_frame(self):
        expected = _valid_pyfeat()
        original = debug_router.detect_frame
        debug_router.detect_frame = lambda *a, **k: expected
        try:
            upload = _FakeUpload(content_type="image/png", data=b"pngbytes")
            result = _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        finally:
            debug_router.detect_frame = original

        self.assertIs(result, expected)
        self.assertIsInstance(result, PyFeatFrameDebug)
        # reasons is always a dict; unavailable numeric fields default to None.
        self.assertIsInstance(result.reasons, dict)

    def test_returns_valid_opensmile_frame(self):
        expected = _valid_opensmile()
        original = debug_router.process_audio_chunk
        debug_router.process_audio_chunk = lambda *a, **k: expected
        try:
            upload = _FakeUpload(content_type="audio/wav", data=b"wavbytes")
            result = _run(
                debug_router.debug_opensmile_audio(
                    audio=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        finally:
            debug_router.process_audio_chunk = original

        self.assertIs(result, expected)
        self.assertIsInstance(result, OpenSmileFrameDebug)
        self.assertIsInstance(result.reasons, dict)


# ---------------------------------------------------------------------------
# Extractor unavailable -> 503 debug-unavailable body (never a 500)
# ---------------------------------------------------------------------------


class DebugExtractorUnavailableTests(unittest.TestCase):
    def _body(self, response: JSONResponse) -> dict:
        return json.loads(bytes(response.body))

    def test_frame_returns_503_openface_unavailable(self):
        def _raise(*args, **kwargs):
            raise OpenFaceDebugUnavailable("no torch")

        original = debug_router.detect_frame
        debug_router.detect_frame = _raise
        try:
            upload = _FakeUpload(content_type="image/jpeg", data=b"jpegbytes")
            response = _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        finally:
            debug_router.detect_frame = original

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        body = self._body(response)
        self.assertEqual(body, {"available": False, "reason": "openface_unavailable"})

    def test_audio_returns_503_opensmile_unavailable(self):
        def _raise(*args, **kwargs):
            raise OpenSmileDebugUnavailable("no opensmile")

        original = debug_router.process_audio_chunk
        debug_router.process_audio_chunk = _raise
        try:
            upload = _FakeUpload(content_type="audio/webm", data=b"webmbytes")
            response = _run(
                debug_router.debug_opensmile_audio(
                    audio=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        finally:
            debug_router.process_audio_chunk = original

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        body = self._body(response)
        self.assertEqual(body, {"available": False, "reason": "opensmile_unavailable"})


# ---------------------------------------------------------------------------
# Upload guards (driven through the coroutine -> _read_capped)
# ---------------------------------------------------------------------------


class DebugUploadGuardTests(unittest.TestCase):
    def test_frame_rejects_unsupported_content_type_with_415(self):
        upload = _FakeUpload(content_type="text/plain", data=b"not-an-image")
        with self.assertRaises(HTTPException) as ctx:
            _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        self.assertEqual(
            ctx.exception.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )

    def test_audio_rejects_unsupported_content_type_with_415(self):
        upload = _FakeUpload(content_type="image/png", data=b"bytes")
        with self.assertRaises(HTTPException) as ctx:
            _run(
                debug_router.debug_opensmile_audio(
                    audio=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        self.assertEqual(
            ctx.exception.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )

    def test_frame_rejects_empty_body_with_400(self):
        upload = _FakeUpload(content_type="image/png", data=b"")
        with self.assertRaises(HTTPException) as ctx:
            _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)

    def test_frame_rejects_oversized_upload_with_413(self):
        # One byte over the 10 MB debug cap.
        oversized = b"x" * (debug_router.MAX_UPLOAD_BYTES + 1)
        upload = _FakeUpload(content_type="image/png", data=oversized)
        with self.assertRaises(HTTPException) as ctx:
            _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        self.assertEqual(
            ctx.exception.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        )

    def test_content_type_with_charset_suffix_is_accepted(self):
        # A "image/png; charset=..." style header must pass the base-type guard.
        expected = _valid_pyfeat()
        original = debug_router.detect_frame
        debug_router.detect_frame = lambda *a, **k: expected
        try:
            upload = _FakeUpload(content_type="image/png; codecs=x", data=b"png")
            result = _run(
                debug_router.debug_openface_frame(
                    frame=upload,
                    frame_timestamp_ms=None,
                    current_user=_current_user(),
                )
            )
        finally:
            debug_router.detect_frame = original
        self.assertIs(result, expected)


# ---------------------------------------------------------------------------
# No persistence: the endpoints take no DB/Session dependency
# ---------------------------------------------------------------------------


class DebugNoPersistenceTests(unittest.TestCase):
    def test_frame_endpoint_has_no_db_dependency(self):
        params = set(inspect.signature(debug_router.debug_openface_frame).parameters)
        # No get_db / Session parameter is present on the debug endpoint.
        self.assertNotIn("db", params)
        self.assertNotIn("session", params)

    def test_audio_endpoint_has_no_db_dependency(self):
        params = set(inspect.signature(debug_router.debug_opensmile_audio).parameters)
        self.assertNotIn("db", params)
        self.assertNotIn("session", params)

    def test_extractor_helpers_do_not_import_database_modules(self):
        # Structural assertion: the pure extractor helpers must not pull in the
        # DB layer (sqlalchemy Session / app.database), keeping them side-effect
        # free with respect to persistence.
        import app.debug.opensmile_debug as opensmile_debug
        import app.debug.openface_debug as openface_debug

        for source in (inspect.getsource(openface_debug), inspect.getsource(opensmile_debug)):
            self.assertNotIn("app.database", source)
            self.assertNotIn("get_db", source)
            self.assertNotIn("Session", source)


# ---------------------------------------------------------------------------
# Schema defaults: availability-aware, None (never 0) and empty reasons
# ---------------------------------------------------------------------------


class DebugSchemaDefaultTests(unittest.TestCase):
    def test_pyfeat_frame_defaults_are_none_not_zero(self):
        frame = PyFeatFrameDebug(
            extractor=ExtractorInfo(name="py-feat", version="2.1.1")
        )
        self.assertFalse(frame.face_detected)
        for field in (
            "face_score",
            "gaze_yaw",
            "gaze_pitch",
            "head_yaw",
            "head_pitch",
            "head_roll",
            "au12",
            "landmarks",
            "image_width",
            "image_height",
            "frame_timestamp_ms",
        ):
            self.assertIsNone(getattr(frame, field), f"{field} should default to None")
        self.assertEqual(frame.reasons, {})

    def test_opensmile_frame_defaults_are_none_not_zero(self):
        frame = OpenSmileFrameDebug()
        for field in ("f0_semitones", "loudness", "voicing", "voicing_kind", "frame_timestamp_ms"):
            self.assertIsNone(getattr(frame, field), f"{field} should default to None")
        self.assertEqual(frame.reasons, {})
        # Feature names sub-model also defaults to all-None.
        self.assertIsNone(frame.feature_names.f0)
        self.assertIsNone(frame.feature_names.loudness)
        self.assertIsNone(frame.feature_names.voicing)
        self.assertEqual(frame.feature_set, "eGeMAPSv02")

    def test_debug_unavailable_is_not_available(self):
        unavailable = DebugUnavailable(reason="openface_unavailable")
        self.assertFalse(unavailable.available)
        self.assertEqual(unavailable.reason, "openface_unavailable")


if __name__ == "__main__":
    unittest.main()
