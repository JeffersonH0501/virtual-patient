"""Unit tests for synchronized interview recording endpoints."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, status

from app.models.user import UserRole
from app.models.medical_interview import RecordingStatus, TurnUpsertRequest
from app.routers.interview_recordings import (
    _attach_student_nonverbal_observations,
    _parse_range,
    _observation_counts,
    _require_owner,
    _require_replay_access,
    _status_for_asset_count,
    _validate_source_durations,
    _without_none,
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


class ObservationContractTests(unittest.TestCase):
    def test_progress_counts_only_canonical_pyfeat_and_student_audio(self) -> None:
        turns = [
            SimpleNamespace(
                speaker="student",
                paraverbal={"speech_rate_wpm": 0},
                nonverbal_features={"visual_alignment_ratio": 0},
            ),
            SimpleNamespace(
                speaker="patient",
                paraverbal=None,
                nonverbal_features=None,
            ),
        ]

        self.assertEqual(
            _observation_counts(
                turns,
                paraverbal_enabled=True,
                pyfeat_enabled=True,
            ),
            (3, 2),
        )

    def test_public_payload_keeps_zero_and_omits_unavailable_values(self) -> None:
        payload = _without_none({
            "visual_alignment_ratio": 0,
            "nod_count": None,
            "nested": {"value": None},
        })

        self.assertEqual(payload, {"visual_alignment_ratio": 0, "nested": {}})

    def test_pyfeat_failure_preserves_turn_transcript(self) -> None:
        turn = SimpleNamespace(
            id="turn-1",
            start_ms=0,
            end_ms=1000,
            speaker="student",
            transcript="Preserved transcript",
            nonverbal_features=None,
        )
        asset = SimpleNamespace(storage_key="student.webm")

        class Query:
            def __init__(self, value):
                self.value = value

            def filter(self, *args):
                return self

            def order_by(self, *args):
                return self

            def first(self):
                return self.value

            def all(self):
                return [self.value]

        class Database:
            def query(self, model):
                return Query(asset if model.__name__ == "InterviewMediaAssetDB" else turn)

        storage = SimpleNamespace(resolve=lambda key: Path(key))
        recording = SimpleNamespace(id="recording-1")
        with patch(
            "app.routers.interview_recordings.settings",
            SimpleNamespace(pyfeat_analysis_enabled=True),
        ), patch(
            "app.routers.interview_recordings.run_in_threadpool",
            new=AsyncMock(side_effect=RuntimeError("extractor failed")),
        ):
            asyncio.run(_attach_student_nonverbal_observations(
                db=Database(),
                storage=storage,
                interview_id=7,
                recording=recording,
            ))

        self.assertEqual(turn.transcript, "Preserved transcript")
        self.assertIsNone(turn.nonverbal_features)
