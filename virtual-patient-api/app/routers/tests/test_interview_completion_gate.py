"""Tests for the interview completion gate and completion metrics."""

import asyncio
import unittest
from types import SimpleNamespace

from app.routers.medical_interviews import (
    _turn_job_outcome_counts,
    _wait_for_multimodal_analysis,
)


class _Query:
    def __init__(self, *, recording=None, pending_count=0):
        self.recording = recording
        self.pending_count = pending_count

    def filter(self, *args):
        del args
        return self

    def first(self):
        return self.recording

    def count(self):
        return self.pending_count


class _Database:
    def __init__(self, status: str, pending_count: int):
        self.recording = SimpleNamespace(
            capture_config={"observation_processing": {"status": status}}
        )
        self.pending_count = pending_count
        self.query_count = 0

    def expire_all(self):
        return None

    def query(self, entity):
        del entity
        self.query_count += 1
        if self.query_count % 2:
            return _Query(recording=self.recording)
        return _Query(pending_count=self.pending_count)


class _CountingQuery:
    def __init__(self, result: int):
        self._result = result

    def filter(self, *args):
        del args
        return self

    def count(self):
        return self._result


class _CountingSession:
    """Returns counts in the fixed order _turn_job_outcome_counts queries them.

    The helper counts completed, then failed, then pending (queued+processing);
    this fake returns ``counts`` in that order so the snapshot can be asserted
    without a real database.
    """

    def __init__(self, counts: list[int]):
        self._counts = list(counts)

    def query(self, entity):
        del entity
        return _CountingQuery(self._counts.pop(0))


class TurnJobOutcomeCountsTests(unittest.TestCase):
    def test_snapshot_groups_finished_and_pending_jobs(self):
        session = _CountingSession([3, 1, 2])  # completed, failed, pending

        snapshot = _turn_job_outcome_counts(session, 70)

        self.assertEqual(
            snapshot,
            {"completed": 3, "failed": 1, "pending": 2, "finished": 4, "total": 6},
        )

    def test_snapshot_is_all_zero_when_no_turn_jobs_exist(self):
        session = _CountingSession([0, 0, 0])

        snapshot = _turn_job_outcome_counts(session, 70)

        self.assertEqual(
            snapshot,
            {"completed": 0, "failed": 0, "pending": 0, "finished": 0, "total": 0},
        )

    def test_snapshot_counts_a_fully_pending_interview_as_unfinished(self):
        session = _CountingSession([0, 0, 5])

        snapshot = _turn_job_outcome_counts(session, 70)

        self.assertEqual(snapshot["finished"], 0)
        self.assertEqual(snapshot["pending"], 5)
        self.assertEqual(snapshot["total"], 5)


class InterviewCompletionGateTests(unittest.TestCase):
    def test_returns_only_when_pipeline_and_turn_jobs_are_terminal(self):
        database = _Database(status="complete", pending_count=0)

        result = asyncio.run(
            _wait_for_multimodal_analysis(database, 70, timeout_seconds=0)
        )

        self.assertEqual(result, "complete")

    def test_does_not_finish_while_a_turn_job_is_pending(self):
        database = _Database(status="complete", pending_count=1)

        with self.assertRaises(TimeoutError):
            asyncio.run(
                _wait_for_multimodal_analysis(database, 70, timeout_seconds=0)
            )

    def test_does_not_finish_while_pipeline_is_queued(self):
        database = _Database(status="queued", pending_count=0)

        with self.assertRaises(TimeoutError):
            asyncio.run(
                _wait_for_multimodal_analysis(database, 70, timeout_seconds=0)
            )


if __name__ == "__main__":
    unittest.main()
