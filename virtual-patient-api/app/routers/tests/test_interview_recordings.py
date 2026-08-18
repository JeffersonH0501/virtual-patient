"""Unit tests for synchronized interview recording endpoints."""

from types import SimpleNamespace
import unittest

from fastapi import HTTPException, status

from app.models.user import UserRole
from app.models.medical_interview import RecordingStatus, TurnUpsertRequest
from app.routers.interview_recordings import (
    _parse_range,
    _require_owner,
    _require_replay_access,
    _status_for_asset_count,
    _validate_source_durations,
)


class RecordingRangeTests(unittest.TestCase):
    def test_full_file_response(self) -> None:
        self.assertEqual(_parse_range(None, 100), (0, 99, status.HTTP_200_OK))

    def test_explicit_and_suffix_ranges(self) -> None:
        self.assertEqual(_parse_range("bytes=10-19", 100), (10, 19, status.HTTP_206_PARTIAL_CONTENT))
        self.assertEqual(_parse_range("bytes=-10", 100), (90, 99, status.HTTP_206_PARTIAL_CONTENT))

    def test_invalid_range_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _parse_range("bytes=200-300", 100)

        self.assertEqual(context.exception.status_code, status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        self.assertEqual(context.exception.headers["Content-Range"], "bytes */100")


class RecordingAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        owner = SimpleNamespace(id=7, organization_id=3)
        self.interview = SimpleNamespace(user_id=7, user=owner)

    def test_only_owner_can_modify_recording(self) -> None:
        _require_owner(self.interview, SimpleNamespace(id=7))
        with self.assertRaises(HTTPException) as context:
            _require_owner(self.interview, SimpleNamespace(id=8))
        self.assertEqual(context.exception.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_in_same_organization_can_replay(self) -> None:
        teacher = SimpleNamespace(id=8, organization_id=3, role=UserRole.TEACHER)
        _require_replay_access(self.interview, teacher)

    def test_student_from_another_account_cannot_replay(self) -> None:
        student = SimpleNamespace(id=8, organization_id=3, role=UserRole.STUDENT)
        with self.assertRaises(HTTPException) as context:
            _require_replay_access(self.interview, student)
        self.assertEqual(context.exception.status_code, status.HTTP_403_FORBIDDEN)


class RecordingDurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uploads = {
            "student_audio": object(),
            "student_video": object(),
            "patient_audio": object(),
            "patient_video": object(),
        }

    def test_four_sources_accept_small_timeline_differences(self) -> None:
        durations = {
            "student_audio": 10_000,
            "student_video": 10_100,
            "patient_audio": 9_900,
            "patient_video": 10_000,
        }

        result = _validate_source_durations(durations, self.uploads, 10_000)

        self.assertEqual(result, durations)

    def test_source_outside_tolerance_is_rejected(self) -> None:
        durations = {kind: 10_000 for kind in self.uploads}
        durations["patient_video"] = 11_000

        with self.assertRaises(HTTPException) as context:
            _validate_source_durations(durations, self.uploads, 10_000)

        self.assertEqual(context.exception.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_missing_source_duration_is_rejected(self) -> None:
        durations = {kind: 10_000 for kind in self.uploads if kind != "patient_audio"}

        with self.assertRaises(HTTPException) as context:
            _validate_source_durations(durations, self.uploads, 10_000)

        self.assertEqual(context.exception.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_overlapping_turns_remain_valid_independent_intervals(self) -> None:
        patient = TurnUpsertRequest(
            speaker="patient",
            sequence=1,
            start_ms=100,
            end_ms=900,
            transcript="Patient speech",
            input_source="tts",
            timing_source="tts_playback",
            timing_quality="measured",
        )
        student = TurnUpsertRequest(
            speaker="student",
            sequence=2,
            start_ms=700,
            end_ms=1_200,
            transcript="Student speech",
            input_source="browser_speech",
            timing_source="browser_speech_events",
            timing_quality="provisional",
        )

        self.assertLess(student.start_ms, patient.end_ms)


class RecordingStatusTests(unittest.TestCase):
    def test_ready_requires_all_four_sources(self) -> None:
        self.assertEqual(_status_for_asset_count(4), RecordingStatus.READY)
        self.assertEqual(_status_for_asset_count(3), RecordingStatus.PARTIAL)
        self.assertEqual(_status_for_asset_count(0), RecordingStatus.UNAVAILABLE)
