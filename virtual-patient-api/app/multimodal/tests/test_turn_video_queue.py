"""Lifecycle tests for the per-turn single-consumer FIFO."""

from threading import enumerate as enumerate_threads
from time import perf_counter

from app.multimodal import turn_video_queue


def test_fifo_is_non_blocking_and_isolates_one_job_failure(monkeypatch):
    processed: list[str] = []

    def fake_process(job_id: str) -> None:
        processed.append(job_id)
        if job_id == "turn-2":
            raise RuntimeError("expected test failure")

    monkeypatch.setattr(turn_video_queue, "_process_job", fake_process)
    turn_video_queue.start_turn_video_worker(recover=False)
    started = perf_counter()
    for job_id in ("turn-1", "turn-2", "turn-3"):
        turn_video_queue.enqueue_turn_video_analysis(job_id)
    enqueue_ms = (perf_counter() - started) * 1000
    turn_video_queue._jobs.join()
    turn_video_queue.shutdown_turn_video_worker(timeout=2)

    assert enqueue_ms < 100
    assert processed == ["turn-1", "turn-2", "turn-3"]
    assert not any(
        thread.name == "turn-video-analysis-worker" for thread in enumerate_threads()
    )
