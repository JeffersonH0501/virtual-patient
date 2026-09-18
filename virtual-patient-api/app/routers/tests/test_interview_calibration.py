"""Tests for the calibration draft contract and the interview start gate.

Calibration is processed temporarily (``POST /calibration/process``) and its
passed result is persisted into ``interview_metadata.calibration`` only when the
interview starts. There is no durable calibration table, so these tests exercise
the draft request contract and the metadata-based start gate.
"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.models.medical_interview import InterviewStatus
from app.routers.medical_interviews import CalibrationResultRequest


_VALID_BASELINE = {
    "baseline_f0_semitones": 4.5,
    "baseline_loudness": 0.6,
    "neutral_head_yaw": 0.1,
    "neutral_head_pitch": 0.2,
    "neutral_head_roll": 0.0,
    "neutral_gaze_yaw": 0.05,
    "neutral_gaze_pitch": 0.07,
}


def calibration_payload(**overrides):
    payload = {
        "version": "multimodal_calibration_v1",
        "status": "passed",
        "failure_reason": None,
        "profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]], "personal_baseline": dict(_VALID_BASELINE)},
        "quality": {"face_valid_ratio": 0.95},
        "personal_baseline": dict(_VALID_BASELINE),
    }
    payload.update(overrides)
    return payload


class CalibrationContractTests(unittest.TestCase):
    def test_passed_result_requires_baseline_and_profile(self):
        # A passed calibration without a personal baseline is rejected.
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                calibration_payload(personal_baseline=None)
            )

    def test_passed_result_requires_profile(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(calibration_payload(profile=None))

    def test_personal_baseline_cannot_be_malformed(self):
        with self.assertRaises(ValidationError):
            CalibrationResultRequest.model_validate(
                calibration_payload(personal_baseline={"baseline_loudness": 0.5})
            )

    def test_passed_result_is_accepted_with_baseline_and_profile(self):
        result = CalibrationResultRequest.model_validate(calibration_payload())
        self.assertEqual(result.status, "passed")
        self.assertIsNotNone(result.personal_baseline)
        self.assertEqual(result.personal_baseline.baseline_f0_semitones, 4.5)

    def test_failed_result_can_omit_baseline_and_profile(self):
        result = CalibrationResultRequest.model_validate(
            calibration_payload(
                status="failed",
                failure_reason="insufficient_audio",
                profile=None,
                quality=None,
                personal_baseline=None,
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_reason, "insufficient_audio")
        self.assertIsNone(result.personal_baseline)


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
            user_id=2,
            status=InterviewStatus.IN_PROGRESS,
            start_time=None,
            interview_metadata={},
        )
        controller = MedicalInterviewController(Database(interview))

        with self.assertRaises(HTTPException) as context:
            controller.start_interview(7)

        self.assertEqual(context.exception.status_code, status.HTTP_409_CONFLICT)

    def test_passed_status_without_valid_baseline_cannot_start(self):
        # A calibration block marked passed but missing a valid baseline must not
        # satisfy the gate.
        interview = SimpleNamespace(
            id=7,
            user_id=2,
            status=InterviewStatus.IN_PROGRESS,
            start_time=None,
            interview_metadata={"calibration": {"status": "passed"}},
        )
        controller = MedicalInterviewController(Database(interview))

        with self.assertRaises(HTTPException) as context:
            controller.start_interview(7)

        self.assertEqual(context.exception.status_code, status.HTTP_409_CONFLICT)

    def test_start_sets_clock_once_and_is_idempotent(self):
        interview = SimpleNamespace(
            id=7,
            user_id=2,
            status=InterviewStatus.IN_PROGRESS,
            start_time=None,
            interview_metadata={
                "calibration": {"status": "passed", "personal_baseline": dict(_VALID_BASELINE)}
            },
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
