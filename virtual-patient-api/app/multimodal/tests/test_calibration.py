"""Numeric calibration contracts and temporary worker-input cleanup.

Private reference persistence is covered by test_calibration_reference.py.
"""

from __future__ import annotations

import asyncio
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.multimodal.calibration import (
    calibration_passed,
    read_calibration,
    read_calibration_profile,
    read_personal_baseline,
)
from app.multimodal.schemas import PersonalBaseline
from app.routers import calibration as calibration_router
from app.routers.calibration import process_calibration_stage
from app.routers.medical_interviews import CalibrationResultRequest



@pytest.fixture(autouse=True)
def isolated_capture_persistence(monkeypatch):
    capture = SimpleNamespace(id="synthetic-capture", result=None)
    monkeypatch.setattr(calibration_router, "preserve_capture", AsyncMock(return_value=capture))
    monkeypatch.setattr("app.controllers.interview_lifecycle.lock_row", lambda *args: capture)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_BASELINE_METRICS = {
    "neutral_head_yaw": -1.2,
    "neutral_head_pitch": 2.3,
    "neutral_head_roll": 0.4,
    "neutral_gaze_yaw": 0.1,
    "neutral_gaze_pitch": -0.2,
}

# Worker outputs that, combined, produce a passing calibration. These mirror the
# shapes emitted by app/nonverbal/calibration_worker.py.
_VIDEO_RESULT_PASS = {
    "profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]], "camera_reference_center": [0.1, -0.2], "gaze_source": "mediapipe_five_point_v1", "calibration_target_count": 5},
    "quality": {"face_valid_ratio": 0.95},
    "passed": True,
    "failure_reason": None,
    "neutral_head": {"neutral_head_yaw": -1.2, "neutral_head_pitch": 2.3, "neutral_head_roll": 0.4},
    "performance": {},
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
    """A calibration metadata JSON that satisfies the five-target protocol."""
    ids = ["CENTER", "TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT"]
    from app.models.calibration import GAZE_TARGETS
    coordinates = {name: (x, y) for name, x, y in GAZE_TARGETS}
    targets = []
    for index, target_id in enumerate(ids):
        start = 2500 + index * 2000
        targets.append({
            "target_id": target_id,
            "target_order": index + 1,
            "target_normalized_x": coordinates[target_id][0],
            "target_normalized_y": coordinates[target_id][1],
            "target_pixel_x": coordinates[target_id][0] * 1280,
            "target_pixel_y": coordinates[target_id][1] * 720,
            "presentation_start_ms": start,
            "presentation_end_ms": start + 2000,
            "observation_window_start_ms": start + 250,
            "observation_window_end_ms": start + 2000,
        })
    camera_start = 2500 + len(ids) * 2000
    metadata = {
        "geometry": {
            "viewport_width": 1280, "viewport_height": 720, "device_pixel_ratio": 1.0,
            "orientation": "landscape", "video_width": 1280, "video_height": 720,
        },
        "targets": targets,
        "gaze_source": "mediapipe_five_point_v1",
        "camera_reference_start_ms": camera_start,
        "camera_reference_end_ms": camera_start + 3000,
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
        self.assertEqual(baseline.neutral_head_yaw, -1.2)
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
            interview_metadata={"calibration": {"profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]], "gaze_source": "mediapipe_five_point_v1"}}}
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




# ---------------------------------------------------------------------------
class ProcessCalibrationStageEndpointTests(unittest.TestCase):
    def test_processes_only_requested_checkpoint_and_deletes_media(self):
        import json

        full_metadata = json.loads(_valid_metadata_json())
        gaze_metadata = {
            "geometry": full_metadata["geometry"],
            "gaze_source": full_metadata["gaze_source"],
            "targets": [
                {
                    **target,
                    "presentation_start_ms": target["presentation_start_ms"] - 2500,
                    "presentation_end_ms": target["presentation_end_ms"] - 2500,
                    "observation_window_start_ms": target["observation_window_start_ms"] - 2500,
                    "observation_window_end_ms": target["observation_window_end_ms"] - 2500,
                }
                for target in full_metadata["targets"]
            ],
            "geometry_stable": True,
        }
        captured = {}

        async def _fake_worker(path, metadata, mode):
            captured["path"] = str(path)
            captured["mode"] = mode
            return ({"passed": True, "failure_reason": None, "profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]]}, "quality": {}}, 0.1)

        with patch.object(calibration_router, "_run_timed_worker", side_effect=_fake_worker):
            response = _run(process_calibration_stage(
                interview_id=42,
                stage="gaze",
                media=_make_upload(b"gaze-webm", filename="gaze.webm", content_type="video/webm"),
                duration_ms=18000,
                metadata_json=json.dumps(gaze_metadata),
                current_user=SimpleNamespace(id=42, role="student"), db=MagicMock(),
            ))

        self.assertEqual(response.status, "passed")
        self.assertEqual(captured["mode"], "gaze")
        self.assertFalse(os.path.exists(captured["path"]))

    def test_rejects_camera_checkpoint_without_gaze_matrix(self):
        import json
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as context:
            _run(process_calibration_stage(
                interview_id=42,
                stage="camera",
                media=_make_upload(b"camera-webm", filename="camera.webm", content_type="video/webm"),
                duration_ms=3000,
                metadata_json=json.dumps({}),
                current_user=SimpleNamespace(id=42, role="student"), db=MagicMock(),
            ))
        self.assertEqual(context.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()


def test_unified_capture_signs_passed_parts_and_deletes_temporary_media(monkeypatch):
    import json
    from app.models.calibration import CameraCalibrationMetadata
    from app.multimodal.calibration_attestation import verify_calibration_checkpoints
    metadata = json.loads(_valid_metadata_json())
    metadata['camera_reference_start_ms'] = max(target['presentation_end_ms'] for target in metadata['targets'])
    metadata['camera_reference_end_ms'] = metadata['camera_reference_start_ms'] + 10000
    camera_metadata = CameraCalibrationMetadata(affine_matrix=[[1, 0, 0], [0, 1, 0]], geometry=metadata['geometry'], geometry_stable=True).model_dump(mode='json')
    paths = []
    for camera_passed in (True, False):
        monkeypatch.setattr(calibration_router, "preserve_capture", AsyncMock(return_value=SimpleNamespace(id="synthetic-capture", result=None)))
        async def worker(path, capture, mode):
            paths.append(path)
            assert mode == 'unified'
            return ({'passed': camera_passed, 'failed_stage': None if camera_passed else 'camera',
                'gaze': dict(_VIDEO_RESULT_PASS), 'camera': {**_VIDEO_RESULT_PASS, 'passed': camera_passed,
                'camera_reference_center': [.5, .1], 'camera_eye_reference': {'center': [0, 0], 'radius': .01}, 'failure_reason': None if camera_passed else 'camera'},
                'camera_metadata': camera_metadata}, .1)
        monkeypatch.setattr(calibration_router, '_run_timed_worker', worker)
        response = _run(process_calibration_stage(stage='unified', interview_id=42,
            media=_make_upload(b'synthetic', filename='calibration.webm', content_type='video/webm'),
            duration_ms=metadata['camera_reference_end_ms'], metadata_json=json.dumps(metadata), current_user=SimpleNamespace(id=42, role='student'), db=MagicMock()))
        checkpoints = response.result['checkpoints']
        assert checkpoints['gaze']['attestation']
        assert bool(checkpoints['camera']['attestation']) == camera_passed
        if camera_passed:
            verify_calibration_checkpoints(42, 42, {key: value['attestation'] for key, value in checkpoints.items()})
        assert not paths[-1].exists()
