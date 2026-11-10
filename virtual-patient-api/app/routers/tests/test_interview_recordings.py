"""Unit tests for synchronized interview recording endpoints."""

from types import SimpleNamespace
import unittest

from fastapi import HTTPException, status
import pytest

from app.media import patient_roi
from app.media.access import _parse_range, _require_owner, _require_replay_access
from app.media.patient_roi import validate_patient_roi as _validate_patient_roi
from app.models.user import UserRole
from app.models.medical_interview import RecordingStatus, TurnUpsertRequest
from app.routers.interview_recordings import (
    _without_none,
)


def test_roi_requires_bounded_ordered_finite_samples(monkeypatch):
    sample = {"timestampMs": 10, "xNormalized": -0.05, "yNormalized": 0.1,
              "widthNormalized": 0.2, "heightNormalized": 0.2}
    monkeypatch.setattr(patient_roi, "MAX_ROI_SNAPSHOTS", 2)
    _validate_patient_roi([sample, {**sample, "timestampMs": 20}], 20)
    for invalid in (
        [sample, sample, sample],
        [{**sample, "timestampMs": 21}],
        [sample, {**sample, "timestampMs": 9}],
        [{**sample, "widthNormalized": float("nan")}],
        [{**sample, "heightNormalized": -0.1}],
        [{**sample, "xNormalized": True}],
        [{**sample, "xNormalized": 2}],
    ):
        with pytest.raises(HTTPException) as error:
            _validate_patient_roi(invalid, 20)
        assert error.value.status_code == 422


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

    def test_teacher_without_assignment_cannot_replay(self) -> None:
        teacher = SimpleNamespace(id=8, organization_id=3, role=UserRole.TEACHER)
        with self.assertRaises(HTTPException):
            _require_replay_access(self.interview, teacher)

    def test_student_from_another_account_cannot_replay(self) -> None:
        student = SimpleNamespace(id=8, organization_id=3, role=UserRole.STUDENT)
        with self.assertRaises(HTTPException) as context:
            _require_replay_access(self.interview, student)
        self.assertEqual(context.exception.status_code, status.HTTP_403_FORBIDDEN)






class ObservationContractTests(unittest.TestCase):
    def test_public_payload_keeps_zero_and_omits_unavailable_values(self) -> None:
        payload = _without_none({
            "visual_alignment_ratio": 0,
            "nod_count": None,
            "nested": {"value": None},
        })

        self.assertEqual(payload, {"visual_alignment_ratio": 0, "nested": {}})


class TurnResponseContractTests(unittest.TestCase):
    """The recap serves the single canonical layered observation schema.

    Per-turn observations are written by the current multimodal pipeline in the
    layered shape (``raw``/``processed``/``base_labels``/``integrated_labels``/
    ``quality``/``versions``/``config_hash``/``status``/``reason``). The recap
    returns that shape verbatim, only stripping unavailable (``None``) optional
    measurements. No legacy conversion happens anymore.
    """

    def _layered_paraverbal(self) -> dict:
        return {
            "raw": {"word_count": 12, "voiced_duration_ms": 3200},
            "processed": {"speech_rate_wpm": 142.0, "articulation_rate_wpm": None},
            "base_labels": {"speech_timing": {"speech_rate_wpm": {"status": "ok", "value": "measured_pace"}}},
            "integrated_labels": {"speech_timing": {"status": "ok", "value": "measured_pace", "reason": None}},
            "quality": {"validRatio": 0.94, "issues": []},
            "versions": {"processing": "1", "thresholds": "1", "label_rules": "1"},
            "config_hash": "abc123",
            "status": "ok",
            "reason": None,
        }

    def _layered_nonverbal(self, status_value: str = "ok") -> dict:
        return {
            "raw": {"sampled_frame_count": 20},
            "processed": {"visual_alignment_ratio": 0.7, "nod_count": 0, "median_visual_alignment_dwell_ms": None},
            "base_labels": {"gaze_orientation": {"visual_alignment_ratio": {"status": "ok", "value": "oriented"}}},
            "integrated_labels": {"gaze_orientation": {"status": status_value, "value": "oriented" if status_value == "ok" else None}},
            "quality": {"sampledFrameCount": 20, "validFrameCount": 18, "issues": []},
            "versions": {"processing": "1", "thresholds": "1", "label_rules": "1"},
            "config_hash": "abc123",
            "status": status_value,
            "reason": None if status_value == "ok" else "insufficient_signal",
        }

    def _turn(self, **overrides):
        base = dict(
            id="t1", message_id=1, speaker="student", start_ms=0, end_ms=4000,
            transcript="hello", input_source="azure_openai_stt",
            timing_source="client_audio_activity", timing_quality="provisional",
            paraverbal=self._layered_paraverbal(), nonverbal_features=self._layered_nonverbal(),
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_student_turn_passes_through_canonical_layered_shape(self) -> None:
        from app.routers.interview_recordings import _turn_response

        response = _turn_response(self._turn())

        # The layered layers survive verbatim (minus null optional metrics).
        self.assertEqual(response.paraverbal["processed"]["speech_rate_wpm"], 142.0)
        self.assertNotIn("articulation_rate_wpm", response.paraverbal["processed"])  # None stripped
        self.assertEqual(response.paraverbal["integrated_labels"]["speech_timing"]["value"], "measured_pace")
        self.assertEqual(response.paraverbal["versions"]["processing"], "1")
        self.assertEqual(response.paraverbal["config_hash"], "abc123")
        self.assertEqual(response.nonverbal_features["processed"]["visual_alignment_ratio"], 0.7)
        self.assertEqual(response.nonverbal_features["processed"]["nod_count"], 0)  # zero preserved
        # No legacy schema marker is added by the recap anymore.
        self.assertNotIn("schema", response.paraverbal)
        self.assertNotIn("schema", response.nonverbal_features)

    def test_patient_turn_has_no_paraverbal_layer(self) -> None:
        from app.routers.interview_recordings import _turn_response

        response = _turn_response(self._turn(speaker="patient", paraverbal=None))

        self.assertIsNone(response.paraverbal)
        self.assertIsNotNone(response.nonverbal_features)

    def test_missing_modality_still_renders(self) -> None:
        # A current-schema modality reported unavailable/partial must still be
        # served (not confused with a legacy shape and not dropped).
        from app.routers.interview_recordings import _turn_response

        response = _turn_response(
            self._turn(nonverbal_features=self._layered_nonverbal(status_value="unavailable"))
        )

        self.assertEqual(response.nonverbal_features["status"], "unavailable")
        self.assertEqual(response.nonverbal_features["reason"], "insufficient_signal")
        self.assertEqual(response.nonverbal_features["integrated_labels"]["gaze_orientation"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
