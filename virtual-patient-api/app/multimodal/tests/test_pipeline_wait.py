"""Do not assemble an interview while its visual work remains pending."""
import asyncio
from types import SimpleNamespace
import pytest
from app.multimodal.pipeline import _wait_for_turn_video_jobs


class FakeDB:
    def __init__(self, jobs):
        self.jobs = jobs

    def expire_all(self):
        pass

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def all(self):
        return self.jobs


def test_completed_jobs_allow_assembly():
    asyncio.run(_wait_for_turn_video_jobs(FakeDB([]), 1, "recording", timeout_seconds=0))


def test_deadline_never_assembles_queued_jobs():
    with pytest.raises(TimeoutError):
        asyncio.run(_wait_for_turn_video_jobs(FakeDB([SimpleNamespace(status="queued")]), 1, "recording", timeout_seconds=0))
