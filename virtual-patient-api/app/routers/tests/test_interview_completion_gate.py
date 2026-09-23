"""Tests for the interview completion gate."""

import asyncio
import unittest
from types import SimpleNamespace

from app.routers.medical_interviews import _wait_for_multimodal_analysis


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
