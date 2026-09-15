"""Tests for the pre-interview technical calibration lifecycle."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.models.medical_interview import InterviewStatus
from app.routers.medical_interviews import CalibrationResultRequest


def calibration_payload(**overrides):
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


class CalibrationContractTests(unittest.TestCase):
    def test_passed_result_requires_voice_and_both_live_devices(self):
        payload = calibration_payload()
        payload["audio"]["voice_detected"] = False

        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(payload)

    def test_personal_baseline_cannot_be_invented(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                calibration_payload(personal_baseline={"baseline_loudness": 0.5})
            )

    def test_failed_result_can_preserve_diagnostic_summary(self):
        payload = calibration_payload(status="failed")
        payload["audio"]["voice_detected"] = False

        result = CalibrationResultRequest.model_validate(payload)

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.audio.voice_detected)

    def test_passed_result_requires_face_detection(self):
        payload = calibration_payload()
        payload["video"]["face_detected"] = False
        payload["video"]["quality_status"] = "inadequate"

        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(payload)

    def test_passed_result_requires_adequate_input_without_clipping(self):
        payload = calibration_payload()
        payload["audio"]["input_level"] = "high"
        payload["audio"]["clipping_detected"] = True

        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(payload)


class Query:
    def __init__(self, interview):
        self.interview = interview

    def filter(self, *args):
        return self

    def first(self):
        return self.interview


class Database:
    def __init__(self, interview):
        self.interview = interview
        self.commit_count = 0

    def query(self, model):
        return Query(self.interview)

    def commit(self):
        self.commit_count += 1

    def refresh(self, value):
        return None


class InterviewStartTests(unittest.TestCase):
    def test_uncalibrated_interview_cannot_start(self):
        interview = SimpleNamespace(
            id=7,
            status=InterviewStatus.IN_PROGRESS,
            start_time=None,
            interview_metadata={},
        )
        controller = MedicalInterviewController(Database(interview))

        with self.assertRaises(HTTPException) as context:
            controller.start_interview(7)

        self.assertEqual(context.exception.status_code, status.HTTP_409_CONFLICT)

    def test_start_sets_clock_once_and_is_idempotent(self):
        interview = SimpleNamespace(
            id=7,
            status=InterviewStatus.IN_PROGRESS,
            start_time=None,
            interview_metadata={"calibration": {"status": "passed"}},
        )
        database = Database(interview)
        controller = MedicalInterviewController(database)
        response = SimpleNamespace(start_time=None)

        with patch(
            "app.controllers.medical_interview_controller.MedicalInterview.from_orm",
            return_value=response,
        ):
            controller.start_interview(7)
            first_start = interview.start_time
            controller.start_interview(7)

        self.assertIsNotNone(first_start)
        self.assertEqual(interview.start_time, first_start)
        self.assertEqual(database.commit_count, 1)
