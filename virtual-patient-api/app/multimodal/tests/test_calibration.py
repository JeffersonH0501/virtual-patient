"""Tests for personal-baseline calibration (Requirements 28.8, 15.3, 15.4, 15.5).

These tests exercise three layers of the calibration feature:

* the pure helpers in ``app.multimodal.calibration``
  (:func:`read_personal_baseline`, :func:`derive_personal_baseline`),
* the relaxed :class:`CalibrationResultRequest` schema guard, and
* the ``POST /{interview_id}/calibration/baseline`` endpoint logic.

Unit vs endpoint coverage
-------------------------
Most cases are unit-level and need neither a live database nor a FastAPI
``TestClient``:

* ``read_personal_baseline`` is tested against lightweight stub objects that only
  expose ``interview_metadata`` (the sole attribute the helper reads).
* ``CalibrationResultRequest`` validation is tested by validating dict payloads
  directly (mirroring ``app/routers/tests/test_interview_calibration.py``).
* ``derive_personal_baseline`` is tested on its guaranteed ``None`` path (no media
  provided), which returns before any extractor import, so it runs without the
  OpenSMILE/Py-Feat dependencies.

The endpoint behaviours (temp media never persisted, values saved, overwrite
guard, calibration allowed before start) are covered by invoking the endpoint
coroutine ``derive_calibration_baseline`` directly with a fake ``Session`` and a
stub interview -- the same lightweight-stub approach used by the existing router
tests -- while mocking :func:`derive_personal_baseline` so no real extractor or
media processing is required. This exercises the real endpoint logic (auth-scoped
lookup, ``start_time`` guard, temp-file streaming + ``finally`` deletion, metadata
persistence) without a live DB or Postgres/Azure/GCS environment.

These tests deliberately do not spin up a FastAPI ``TestClient`` against a real
database: that would require Postgres/Azure/LiveKit/GCS configuration that is not
part of a unit-test environment, per the workspace validation rules. Calling the
endpoint coroutine directly gives the strongest feasible coverage of the endpoint
contract without fabricating an environment.
"""

from __future__ import annotations

import asyncio
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.multimodal.calibration import (
    derive_personal_baseline,
    read_personal_baseline,
)
from app.multimodal.schemas import PersonalBaseline
from app.routers import medical_interviews
from app.routers.medical_interviews import (
    CalibrationResultRequest,
    derive_calibration_baseline,
)


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

# A fully-specified, numeric-only baseline used across the tests. Fundamental
# frequency is in semitones only (never Hertz), matching the schema.
_VALID_BASELINE_METRICS = {
    "baseline_f0_semitones": 4.5,
    "baseline_loudness": 0.62,
    "neutral_head_yaw": -1.2,
    "neutral_head_pitch": 2.3,
    "neutral_head_roll": 0.4,
    "neutral_gaze_yaw": 0.1,
    "neutral_gaze_pitch": -0.2,
}


def _valid_baseline() -> PersonalBaseline:
    return PersonalBaseline(**_VALID_BASELINE_METRICS)


def calibration_payload(**overrides):
    """Build a valid ``CalibrationResultRequest`` payload.

    Mirrors the helper in ``app/routers/tests/test_interview_calibration.py`` so
    the two suites agree on what a well-formed calibration summary looks like.
    """
    payload = {
        "version": "technical_v2",
        "status": "passed",
        "duration_ms": 20_000,
        "recording_supported": True,
        "audio": {
            "microphone_available": True,
            "stream_active": True,
            "voice_detected": True,
            "input_level": "adequate",
            "clipping_detected": False,
        },
        "video": {
            "camera_available": True,
            "stream_active": True,
            "face_detected": True,
            "face_detection_rate": 95.0,
            "quality_status": "adequate",
        },
        "personal_baseline": None,
    }
    payload.update(overrides)
    return payload


def _make_upload(content: bytes, *, filename: str, content_type: str) -> UploadFile:
    """Build a real Starlette ``UploadFile`` backed by an in-memory buffer.

    The endpoint reads the upload through ``await upload.seek/read``; a real
    ``UploadFile`` over a ``BytesIO`` exercises that streaming path without a
    multipart HTTP request.
    """
    headers = Headers({"content-type": content_type})
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=headers)


class _Query:
    """Minimal SQLAlchemy ``Query`` stub returning a fixed interview."""

    def __init__(self, interview):
        self._interview = interview

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._interview


class _Database:
    """Minimal ``Session`` stub recording commits."""

    def __init__(self, interview):
        self._interview = interview
        self.commit_count = 0

    def query(self, model):
        return _Query(self._interview)

    def commit(self):
        self.commit_count += 1


def _run(coro):
    """Run an async endpoint coroutine to completion for a sync test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# read_personal_baseline -- the pipeline's single baseline accessor
# ---------------------------------------------------------------------------


class ReadPersonalBaselineTests(unittest.TestCase):
    def test_reads_valid_baseline_from_metadata(self):
        interview = SimpleNamespace(
            interview_metadata={
                "calibration": {"personal_baseline": dict(_VALID_BASELINE_METRICS)}
            }
        )

        baseline = read_personal_baseline(interview)

        self.assertIsInstance(baseline, PersonalBaseline)
        self.assertEqual(baseline.baseline_f0_semitones, 4.5)
        self.assertEqual(baseline.neutral_gaze_yaw, 0.1)

    def test_returns_none_when_interview_is_none(self):
        self.assertIsNone(read_personal_baseline(None))

    def test_returns_none_when_metadata_absent(self):
        interview = SimpleNamespace(interview_metadata=None)
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_calibration_block_absent(self):
        interview = SimpleNamespace(interview_metadata={"other": {}})
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_baseline_absent(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"status": "passed"}}
        )
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_stored_payload_is_malformed(self):
        # Missing the required ``baseline_f0_semitones`` -> schema validation fails
        # and the helper degrades to ``None`` rather than raising.
        interview = SimpleNamespace(
            interview_metadata={
                "calibration": {"personal_baseline": {"baseline_loudness": 0.5}}
            }
        )
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_stored_payload_is_not_a_dict(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"personal_baseline": "nope"}}
        )
        self.assertIsNone(read_personal_baseline(interview))


# ---------------------------------------------------------------------------
# CalibrationResultRequest -- relaxed schema guard (Requirement 15.5)
# ---------------------------------------------------------------------------


class CalibrationResultRequestBaselineTests(unittest.TestCase):
    def test_accepts_valid_numeric_baseline(self):
        # The old "not implemented" rejection is gone: a well-formed, numeric-only
        # baseline no longer raises.
        result = CalibrationResultRequest.model_validate(
            calibration_payload(personal_baseline=dict(_VALID_BASELINE_METRICS))
        )

        self.assertIsInstance(result.personal_baseline, PersonalBaseline)
        self.assertEqual(result.personal_baseline.baseline_f0_semitones, 4.5)

    def test_accepts_baseline_without_optional_gaze(self):
        metrics = {
            k: v
            for k, v in _VALID_BASELINE_METRICS.items()
            if k not in {"neutral_gaze_yaw", "neutral_gaze_pitch"}
        }
        result = CalibrationResultRequest.model_validate(
            calibration_payload(personal_baseline=metrics)
        )

        self.assertIsNone(result.personal_baseline.neutral_gaze_yaw)
        self.assertIsNone(result.personal_baseline.neutral_gaze_pitch)

    def test_none_baseline_is_still_accepted(self):
        result = CalibrationResultRequest.model_validate(
            calibration_payload(personal_baseline=None)
        )
        self.assertIsNone(result.personal_baseline)

    def test_rejects_baseline_missing_required_field(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                calibration_payload(personal_baseline={"baseline_loudness": 0.5})
            )

    def test_rejects_baseline_with_wrong_types(self):
        bad = dict(_VALID_BASELINE_METRICS)
        bad["baseline_f0_semitones"] = "not-a-number"
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                calibration_payload(personal_baseline=bad)
            )


# ---------------------------------------------------------------------------
# derive_personal_baseline -- no fabrication when no media is provided
# ---------------------------------------------------------------------------


class DerivePersonalBaselineTests(unittest.TestCase):
    def test_returns_none_when_no_media_provided(self):
        # With neither audio nor video, the required metric groups cannot be
        # derived; the helper returns None before importing any extractor, so
        # this path holds even without the OpenSMILE/Py-Feat dependencies.
        self.assertIsNone(
            derive_personal_baseline(audio_path=None, video_path=None)
        )

    def test_returns_none_and_does_not_fabricate_values(self):
        result = derive_personal_baseline(
            audio_path=None, video_path=None, min_voiced_duration_ms=300
        )
        # No PersonalBaseline object is fabricated when media is unavailable.
        self.assertNotIsInstance(result, PersonalBaseline)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# POST /{interview_id}/calibration/baseline -- endpoint logic
# ---------------------------------------------------------------------------


class DeriveCalibrationBaselineEndpointTests(unittest.TestCase):
    def _interview(self, **overrides):
        base = {
            "id": 7,
            "user_id": 42,
            "status": "in_progress",
            "start_time": None,
            "interview_metadata": {},
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def _current_user(self):
        return SimpleNamespace(id=42)

    def test_requires_at_least_one_media(self):
        interview = self._interview()
        db = _Database(interview)

        with self.assertRaises(HTTPException) as ctx:
            _run(
                derive_calibration_baseline(
                    interview_id=7,
                    audio=None,
                    video=None,
                    current_user=self._current_user(),
                    db=db,
                )
            )

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_when_interview_not_found(self):
        db = _Database(None)
        audio = _make_upload(b"x", filename="c.wav", content_type="audio/wav")

        with self.assertRaises(HTTPException) as ctx:
            _run(
                derive_calibration_baseline(
                    interview_id=7,
                    audio=audio,
                    video=None,
                    current_user=self._current_user(),
                    db=db,
                )
            )

        self.assertEqual(ctx.exception.status_code, status.HTTP_404_NOT_FOUND)

    def test_allows_calibration_before_start_and_saves_numeric_values(self):
        # Overwrite guard: calibration is allowed while start_time is None.
        interview = self._interview(start_time=None)
        db = _Database(interview)
        audio = _make_upload(b"audio-bytes", filename="c.wav", content_type="audio/wav")
        video = _make_upload(b"video-bytes", filename="c.mp4", content_type="video/mp4")

        derived = _valid_baseline()
        with patch.object(
            medical_interviews, "derive_personal_baseline", return_value=derived
        ) as mock_derive, patch.object(
            medical_interviews, "flag_modified"
        ), patch.object(
            medical_interviews, "settings",
            SimpleNamespace(paraverbal_min_voiced_duration_ms=300),
        ):
            response = _run(
                derive_calibration_baseline(
                    interview_id=7,
                    audio=audio,
                    video=video,
                    current_user=self._current_user(),
                    db=db,
                )
            )

        # Endpoint reports success and echoes the derived baseline.
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.personal_baseline, derived)

        # Values saved: numeric metrics land under
        # interview_metadata.calibration.personal_baseline.
        stored = interview.interview_metadata["calibration"]["personal_baseline"]
        self.assertEqual(stored, _VALID_BASELINE_METRICS)
        self.assertEqual(db.commit_count, 1)

        # Baseline accessible from the pipeline: the stored payload round-trips
        # through the pipeline's single accessor.
        pipeline_view = read_personal_baseline(interview)
        self.assertEqual(pipeline_view, derived)

        # The derivation was invoked with a real temp audio and video path.
        _, kwargs = mock_derive.call_args
        self.assertIsNotNone(kwargs["audio_path"])
        self.assertIsNotNone(kwargs["video_path"])

    def test_media_not_persisted_temp_files_deleted(self):
        # Media is never persisted (Requirement 15.4): the temp files handed to
        # the extractor must not exist once the endpoint returns.
        interview = self._interview()
        db = _Database(interview)
        audio = _make_upload(b"audio-bytes", filename="c.wav", content_type="audio/wav")
        video = _make_upload(b"video-bytes", filename="c.mp4", content_type="video/mp4")

        captured = {}

        def _capture(*, audio_path, video_path, min_voiced_duration_ms=None):
            # Files exist while the extractor runs...
            captured["audio_path"] = audio_path
            captured["video_path"] = video_path
            captured["audio_exists_during"] = os.path.exists(audio_path)
            captured["video_exists_during"] = os.path.exists(video_path)
            return _valid_baseline()

        with patch.object(
            medical_interviews, "derive_personal_baseline", side_effect=_capture
        ), patch.object(
            medical_interviews, "flag_modified"
        ), patch.object(
            medical_interviews, "settings",
            SimpleNamespace(paraverbal_min_voiced_duration_ms=300),
        ):
            _run(
                derive_calibration_baseline(
                    interview_id=7,
                    audio=audio,
                    video=video,
                    current_user=self._current_user(),
                    db=db,
                )
            )

        self.assertTrue(captured["audio_exists_during"])
        self.assertTrue(captured["video_exists_during"])
        # ...and are removed by the finally block once the endpoint returns.
        self.assertFalse(os.path.exists(captured["audio_path"]))
        self.assertFalse(os.path.exists(captured["video_path"]))

    def test_temp_files_deleted_even_when_derivation_fails(self):
        interview = self._interview()
        db = _Database(interview)
        audio = _make_upload(b"audio-bytes", filename="c.wav", content_type="audio/wav")

        captured = {}

        def _boom(*, audio_path, video_path, min_voiced_duration_ms=None):
            captured["audio_path"] = audio_path
            raise RuntimeError("extractor blew up")

        with patch.object(
            medical_interviews, "derive_personal_baseline", side_effect=_boom
        ), patch.object(
            medical_interviews, "settings",
            SimpleNamespace(paraverbal_min_voiced_duration_ms=300),
        ):
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    derive_calibration_baseline(
                        interview_id=7,
                        audio=audio,
                        video=None,
                        current_user=self._current_user(),
                        db=db,
                    )
                )

        self.assertEqual(
            ctx.exception.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        # The temp file is deleted by the finally block despite the failure.
        self.assertFalse(os.path.exists(captured["audio_path"]))

    def test_unavailable_baseline_is_not_fabricated(self):
        interview = self._interview()
        db = _Database(interview)
        audio = _make_upload(b"audio-bytes", filename="c.wav", content_type="audio/wav")

        with patch.object(
            medical_interviews, "derive_personal_baseline", return_value=None
        ), patch.object(
            medical_interviews, "settings",
            SimpleNamespace(paraverbal_min_voiced_duration_ms=300),
        ):
            response = _run(
                derive_calibration_baseline(
                    interview_id=7,
                    audio=audio,
                    video=None,
                    current_user=self._current_user(),
                    db=db,
                )
            )

        self.assertEqual(response.status, "unavailable")
        self.assertIsNone(response.personal_baseline)
        # Nothing persisted and no baseline invented.
        self.assertNotIn("calibration", interview.interview_metadata)
        self.assertEqual(db.commit_count, 0)

    def test_overwrite_prevented_once_started(self):
        # Overwrite guard: once start_time is set, the baseline endpoint rejects
        # with 409 before touching media.
        interview = self._interview(start_time="2024-01-01T00:00:00+00:00")
        db = _Database(interview)
        audio = _make_upload(b"audio-bytes", filename="c.wav", content_type="audio/wav")

        with patch.object(
            medical_interviews, "derive_personal_baseline"
        ) as mock_derive:
            with self.assertRaises(HTTPException) as ctx:
                _run(
                    derive_calibration_baseline(
                        interview_id=7,
                        audio=audio,
                        video=None,
                        current_user=self._current_user(),
                        db=db,
                    )
                )

        self.assertEqual(ctx.exception.status_code, status.HTTP_409_CONFLICT)
        # The guard short-circuits before any derivation attempt.
        mock_derive.assert_not_called()


if __name__ == "__main__":
    unittest.main()
