"""Tests for the temporary calibration flow and personal-baseline accessors.

Calibration is processed temporarily (``POST /calibration/process``) with no
database row and no permanent media, and its passed result is persisted into
``interview_metadata.calibration`` only when the interview starts. These tests
cover:

* the pipeline accessors :func:`read_personal_baseline` and
  :func:`read_calibration_profile`;
* the no-fabrication guarantee of :func:`derive_personal_baseline`;
* the draft :class:`CalibrationResultRequest` schema guard;
* the result assembly (:func:`_assemble_result`) shared with the old durable flow
  so a valid calibration is functionally equivalent; and
* the temporary-processing endpoint contract (temp file always deleted on pass,
  fail, and worker failure) exercised by calling the endpoint coroutine directly
  with mocked isolated workers -- no live DB, media, or external environment.
"""

from __future__ import annotations

import asyncio
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.multimodal.calibration import (
    calibration_passed,
    derive_personal_baseline,
    read_calibration,
    read_calibration_profile,
    read_personal_baseline,
)
from app.multimodal.schemas import PersonalBaseline
from app.routers import calibration as calibration_router
from app.routers.calibration import _assemble_result, process_calibration
from app.routers.medical_interviews import CalibrationResultRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_BASELINE_METRICS = {
    "baseline_f0_semitones": 4.5,
    "baseline_loudness": 0.62,
    "neutral_head_yaw": -1.2,
    "neutral_head_pitch": 2.3,
    "neutral_head_roll": 0.4,
    "neutral_gaze_yaw": 0.1,
    "neutral_gaze_pitch": -0.2,
}

# Worker outputs that, combined, produce a passing calibration. These mirror the
# shapes emitted by app/nonverbal/calibration_worker.py.
_VIDEO_RESULT_PASS = {
    "profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]], "camera_reference_center": [0.1, -0.2]},
    "quality": {"face_valid_ratio": 0.95},
    "passed": True,
    "failure_reason": None,
    "neutral_head": {"neutral_head_yaw": -1.2, "neutral_head_pitch": 2.3, "neutral_head_roll": 0.4},
    "performance": {},
}
_AUDIO_RESULT_PASS = {
    "voiced_duration_ms": 9000,
    "clipping_detected": False,
    "baseline_f0_semitones": 4.5,
    "baseline_loudness": 0.62,
}


def draft_payload(**overrides):
    payload = {
        "version": "multimodal_calibration_v1",
        "status": "passed",
        "failure_reason": None,
        "profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]], "personal_baseline": dict(_VALID_BASELINE_METRICS)},
        "quality": {"face_valid_ratio": 0.95},
        "personal_baseline": dict(_VALID_BASELINE_METRICS),
    }
    payload.update(overrides)
    return payload


def _make_upload(content: bytes, *, filename: str, content_type: str) -> UploadFile:
    headers = Headers({"content-type": content_type})
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=headers)


def _valid_metadata_json() -> str:
    """A calibration metadata JSON that satisfies the 9-target protocol."""
    ids = ["CENTER", "TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT", "TOP_CENTER", "BOTTOM_CENTER", "MIDDLE_LEFT", "MIDDLE_RIGHT"]
    targets = []
    for index, target_id in enumerate(ids):
        start = 2500 + index * 2000
        targets.append({
            "target_id": target_id,
            "target_order": index + 1,
            "target_normalized_x": 0.5,
            "target_normalized_y": 0.5,
            "target_pixel_x": 640.0,
            "target_pixel_y": 360.0,
            "presentation_start_ms": start,
            "presentation_end_ms": start + 2000,
            "observation_window_start_ms": start + 250,
            "observation_window_end_ms": start + 2000,
        })
    camera_start = 2500 + 9 * 2000
    metadata = {
        "geometry": {
            "viewport_width": 1280, "viewport_height": 720, "device_pixel_ratio": 1.0,
            "orientation": "landscape", "video_width": 1280, "video_height": 720,
        },
        "targets": targets,
        "camera_reference_start_ms": camera_start,
        "camera_reference_end_ms": camera_start + 3000,
        "voice_baseline_start_ms": camera_start + 3000,
        "voice_baseline_end_ms": camera_start + 3000 + 9000,
        "geometry_stable": True,
    }
    import json
    return json.dumps(metadata)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# read_personal_baseline / read_calibration_profile -- pipeline accessors
# ---------------------------------------------------------------------------


class ReadPersonalBaselineTests(unittest.TestCase):
    def test_reads_valid_baseline_from_metadata(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"personal_baseline": dict(_VALID_BASELINE_METRICS)}}
        )
        baseline = read_personal_baseline(interview)
        self.assertIsInstance(baseline, PersonalBaseline)
        self.assertEqual(baseline.baseline_f0_semitones, 4.5)
        self.assertEqual(baseline.neutral_gaze_yaw, 0.1)

    def test_returns_none_when_interview_is_none(self):
        self.assertIsNone(read_personal_baseline(None))

    def test_returns_none_when_metadata_absent(self):
        self.assertIsNone(read_personal_baseline(SimpleNamespace(interview_metadata=None)))

    def test_returns_none_when_calibration_block_absent(self):
        self.assertIsNone(read_personal_baseline(SimpleNamespace(interview_metadata={"other": {}})))

    def test_returns_none_when_baseline_absent(self):
        interview = SimpleNamespace(interview_metadata={"calibration": {"status": "passed"}})
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_stored_payload_is_malformed(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"personal_baseline": {"baseline_loudness": 0.5}}}
        )
        self.assertIsNone(read_personal_baseline(interview))

    def test_returns_none_when_stored_payload_is_not_a_dict(self):
        interview = SimpleNamespace(interview_metadata={"calibration": {"personal_baseline": "nope"}})
        self.assertIsNone(read_personal_baseline(interview))


class ReadCalibrationProfileTests(unittest.TestCase):
    def test_reads_profile_from_metadata(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]]}}}
        )
        profile = read_calibration_profile(interview)
        self.assertIsInstance(profile, dict)
        self.assertIn("affine_matrix", profile)

    def test_returns_none_when_absent_or_invalid(self):
        self.assertIsNone(read_calibration_profile(None))
        self.assertIsNone(read_calibration_profile(SimpleNamespace(interview_metadata={})))
        self.assertIsNone(
            read_calibration_profile(SimpleNamespace(interview_metadata={"calibration": {"profile": "nope"}}))
        )


class ReadCalibrationTests(unittest.TestCase):
    def test_reads_calibration_block_from_metadata(self):
        block = {"status": "passed", "profile": {"affine_matrix": []}, "personal_baseline": dict(_VALID_BASELINE_METRICS)}
        interview = SimpleNamespace(interview_metadata={"calibration": block})
        self.assertEqual(read_calibration(interview), block)

    def test_returns_none_when_absent_or_invalid(self):
        self.assertIsNone(read_calibration(None))
        self.assertIsNone(read_calibration(SimpleNamespace(interview_metadata=None)))
        self.assertIsNone(read_calibration(SimpleNamespace(interview_metadata={"other": {}}))
                          )
        self.assertIsNone(read_calibration(SimpleNamespace(interview_metadata={"calibration": "nope"})))


class CalibrationPassedTests(unittest.TestCase):
    """The interview-start gate: passed status + a valid persisted baseline."""

    def test_true_when_passed_with_valid_baseline(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"status": "passed", "personal_baseline": dict(_VALID_BASELINE_METRICS)}}
        )
        self.assertTrue(calibration_passed(interview))

    def test_false_when_no_calibration(self):
        self.assertFalse(calibration_passed(None))
        self.assertFalse(calibration_passed(SimpleNamespace(interview_metadata={})))

    def test_false_when_status_not_passed(self):
        interview = SimpleNamespace(
            interview_metadata={"calibration": {"status": "failed", "personal_baseline": dict(_VALID_BASELINE_METRICS)}}
        )
        self.assertFalse(calibration_passed(interview))

    def test_false_when_passed_but_baseline_missing_or_invalid(self):
        # Passed status but no baseline -> not usable to start.
        self.assertFalse(
            calibration_passed(SimpleNamespace(interview_metadata={"calibration": {"status": "passed"}}))
        )
        # Passed status but malformed baseline -> not usable to start.
        self.assertFalse(
            calibration_passed(
                SimpleNamespace(
                    interview_metadata={"calibration": {"status": "passed", "personal_baseline": {"baseline_loudness": 0.5}}}
                )
            )
        )


# ---------------------------------------------------------------------------
# CalibrationResultRequest -- draft schema guard
# ---------------------------------------------------------------------------


class CalibrationResultRequestTests(unittest.TestCase):
    def test_accepts_passed_draft_with_baseline_and_profile(self):
        result = CalibrationResultRequest.model_validate(draft_payload())
        self.assertEqual(result.status, "passed")
        self.assertIsInstance(result.personal_baseline, PersonalBaseline)

    def test_rejects_passed_without_baseline(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(draft_payload(personal_baseline=None))

    def test_rejects_passed_without_profile(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(draft_payload(profile=None))

    def test_rejects_malformed_baseline(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                draft_payload(personal_baseline={"baseline_loudness": 0.5})
            )

    def test_accepts_failed_without_baseline(self):
        result = CalibrationResultRequest.model_validate(
            draft_payload(status="failed", failure_reason="insufficient_audio", profile=None, quality=None, personal_baseline=None)
        )
        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.personal_baseline)


# ---------------------------------------------------------------------------
# derive_personal_baseline -- no fabrication when no media is provided
# ---------------------------------------------------------------------------


class DerivePersonalBaselineTests(unittest.TestCase):
    def test_returns_none_when_no_media_provided(self):
        self.assertIsNone(derive_personal_baseline(audio_path=None, video_path=None))

    def test_returns_none_and_does_not_fabricate_values(self):
        result = derive_personal_baseline(audio_path=None, video_path=None, min_voiced_duration_ms=300)
        self.assertNotIsInstance(result, PersonalBaseline)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _assemble_result -- functional equivalence with the old durable assembly
# ---------------------------------------------------------------------------


class AssembleResultTests(unittest.TestCase):
    def test_passed_assembles_personal_baseline_and_status(self):
        status_, reason, profile, quality, baseline = _assemble_result(
            dict(_VIDEO_RESULT_PASS), dict(_AUDIO_RESULT_PASS)
        )
        self.assertEqual(status_, "passed")
        self.assertIsNone(reason)
        self.assertIsNotNone(baseline)
        # Baseline merges neutral head + audio F0/loudness + gaze from camera center.
        self.assertEqual(baseline["baseline_f0_semitones"], 4.5)
        self.assertEqual(baseline["baseline_loudness"], 0.62)
        self.assertEqual(baseline["neutral_gaze_yaw"], 0.1)
        self.assertEqual(baseline["neutral_gaze_pitch"], -0.2)
        self.assertEqual(baseline["neutral_head_yaw"], -1.2)
        # Quality is patched with the audio-derived fields.
        self.assertEqual(quality["valid_speech_duration_ms"], 9000)
        self.assertFalse(quality["clipping_detected"])

    def test_failed_when_audio_insufficient(self):
        audio = dict(_AUDIO_RESULT_PASS, voiced_duration_ms=1000)
        status_, reason, profile, quality, baseline = _assemble_result(
            dict(_VIDEO_RESULT_PASS), audio
        )
        self.assertEqual(status_, "failed")
        self.assertIsNone(baseline)
        self.assertEqual(reason, "insufficient_audio")

    def test_failed_when_clipping_detected(self):
        audio = dict(_AUDIO_RESULT_PASS, clipping_detected=True)
        status_, reason, profile, quality, baseline = _assemble_result(
            dict(_VIDEO_RESULT_PASS), audio
        )
        self.assertEqual(status_, "failed")
        self.assertIsNone(baseline)

    def test_failed_propagates_video_failure_reason(self):
        video = dict(_VIDEO_RESULT_PASS, passed=False, failure_reason="gaze_coverage")
        status_, reason, profile, quality, baseline = _assemble_result(
            video, dict(_AUDIO_RESULT_PASS)
        )
        self.assertEqual(status_, "failed")
        self.assertEqual(reason, "gaze_coverage")


# ---------------------------------------------------------------------------
# POST /calibration/process -- temporary processing endpoint contract
# ---------------------------------------------------------------------------


class ProcessCalibrationEndpointTests(unittest.TestCase):
    def _current_user(self):
        return SimpleNamespace(id=42)

    def test_passes_and_deletes_temp_file(self):
        video = _make_upload(b"combined-webm-bytes", filename="c.webm", content_type="video/webm")
        captured = {}

        async def _fake_worker(path, metadata, mode):
            captured.setdefault("paths", []).append(str(path))
            captured["exists_during"] = os.path.exists(path)
            return dict(_VIDEO_RESULT_PASS) if mode == "video" else dict(_AUDIO_RESULT_PASS)

        with patch.object(calibration_router, "_run_isolated_worker", side_effect=_fake_worker):
            response = _run(
                process_calibration(
                    video=video,
                    duration_ms=33000,
                    metadata_json=_valid_metadata_json(),
                    current_user=self._current_user(),
                    db=SimpleNamespace(),
                )
            )

        self.assertEqual(response.status, "passed")
        self.assertIsNone(response.failure_reason)
        self.assertIsNotNone(response.personal_baseline)
        # The same temp path was used by both workers and is removed afterwards.
        self.assertTrue(captured["exists_during"])
        self.assertFalse(os.path.exists(captured["paths"][0]))

    def test_failed_result_still_deletes_temp_file(self):
        video = _make_upload(b"combined-webm-bytes", filename="c.webm", content_type="video/webm")
        captured = {}

        async def _fake_worker(path, metadata, mode):
            captured["path"] = str(path)
            if mode == "video":
                return dict(_VIDEO_RESULT_PASS, passed=False, failure_reason="gaze_coverage")
            return dict(_AUDIO_RESULT_PASS)

        with patch.object(calibration_router, "_run_isolated_worker", side_effect=_fake_worker):
            response = _run(
                process_calibration(
                    video=video,
                    duration_ms=33000,
                    metadata_json=_valid_metadata_json(),
                    current_user=self._current_user(),
                    db=SimpleNamespace(),
                )
            )

        self.assertEqual(response.status, "failed")
        self.assertEqual(response.failure_reason, "gaze_coverage")
        self.assertIsNone(response.personal_baseline)
        self.assertFalse(os.path.exists(captured["path"]))

    def test_worker_failure_returns_controlled_result_and_deletes_temp(self):
        video = _make_upload(b"combined-webm-bytes", filename="c.webm", content_type="video/webm")
        captured = {}

        async def _boom(path, metadata, mode):
            captured["path"] = str(path)
            raise RuntimeError("native worker crashed")

        with patch.object(calibration_router, "_run_isolated_worker", side_effect=_boom):
            response = _run(
                process_calibration(
                    video=video,
                    duration_ms=33000,
                    metadata_json=_valid_metadata_json(),
                    current_user=self._current_user(),
                    db=SimpleNamespace(),
                )
            )

        self.assertEqual(response.status, "failed")
        self.assertEqual(response.failure_reason, "processing_failed")
        self.assertIsNone(response.personal_baseline)
        # The temp file is deleted even when a worker crashes.
        self.assertFalse(os.path.exists(captured["path"]))

    def test_rejects_unsupported_media_type(self):
        from fastapi import HTTPException
        video = _make_upload(b"x", filename="c.avi", content_type="video/avi")
        with self.assertRaises(HTTPException) as ctx:
            _run(
                process_calibration(
                    video=video,
                    duration_ms=33000,
                    metadata_json=_valid_metadata_json(),
                    current_user=self._current_user(),
                    db=SimpleNamespace(),
                )
            )
        self.assertEqual(ctx.exception.status_code, 415)

    def test_rejects_invalid_metadata(self):
        from fastapi import HTTPException
        video = _make_upload(b"x", filename="c.webm", content_type="video/webm")
        with self.assertRaises(HTTPException) as ctx:
            _run(
                process_calibration(
                    video=video,
                    duration_ms=30000,
                    metadata_json="{not valid json",
                    current_user=self._current_user(),
                    db=SimpleNamespace(),
                )
            )
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
