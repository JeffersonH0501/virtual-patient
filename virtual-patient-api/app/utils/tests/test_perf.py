"""Focused tests for the performance-observability helper.

Cover correlation (trace_id), measurement (duration), status handling on
success/error, the enable/disable toggle, and the non-blocking guarantee.
"""

import logging

import pytest

from app.utils import perf


def _events(caplog):
    return [r.message for r in caplog.records if r.message.startswith("performance_event")]


def test_track_success_emits_duration_status_and_trace_id(caplog):
    perf.set_trace_id("trace-abc")
    try:
        with caplog.at_level(logging.INFO, logger="app.perf"):
            with perf.track("conversation", "stt", audio_bytes=1024) as event:
                event["chars"] = 42
    finally:
        perf.set_trace_id(None)

    (line,) = _events(caplog)
    assert "component=conversation" in line
    assert "operation=stt" in line
    assert "phase=complete" in line
    assert "status=success" in line
    assert "trace_id=trace-abc" in line
    assert "audio_bytes=1024" in line
    assert "chars=42" in line
    assert "duration_ms=" in line


def test_track_error_emits_error_phase_and_reraises(caplog):
    with caplog.at_level(logging.INFO, logger="app.perf"):
        with pytest.raises(ValueError):
            with perf.track("evaluation", "multimodal_evaluation", trace_id="t1"):
                raise ValueError("boom")

    (line,) = _events(caplog)
    assert "phase=error" in line
    assert "status=error" in line
    assert "error_type=ValueError" in line
    assert "trace_id=t1" in line


def test_explicit_trace_id_overrides_context(caplog):
    perf.set_trace_id("context-id")
    try:
        with caplog.at_level(logging.INFO, logger="app.perf"):
            perf.perf_event("multimodal_pipeline", "stages", trace_id="explicit-id")
    finally:
        perf.set_trace_id(None)
    (line,) = _events(caplog)
    assert "trace_id=explicit-id" in line


def test_values_are_single_tokens(caplog):
    with caplog.at_level(logging.INFO, logger="app.perf"):
        perf.perf_event("c", "o", note="two words", ratio=0.5, flag=True, missing=None)
    (line,) = _events(caplog)
    # Whitespace in a value would break one-line grepping; it must be collapsed.
    assert "note=two_words" in line
    assert "ratio=0.500" in line
    assert "flag=true" in line
    assert "missing=none" in line


def test_events_are_always_enabled(caplog):
    with caplog.at_level(logging.INFO, logger="app.perf"):
        perf.perf_event("c", "o")
        with perf.track("c", "o"):
            pass
    assert len(_events(caplog)) == 2


def test_track_is_non_blocking_when_logging_fails(monkeypatch):
    # A logging failure must never surface into the measured operation.
    def explode(*_args, **_kwargs):
        raise RuntimeError("logging backend down")

    monkeypatch.setattr(perf.logger, "info", explode)
    with perf.track("c", "o") as event:
        event["ok"] = 1  # the block still runs and returns normally


def test_active_gauge_counts_concurrent_operations_and_is_thread_safe():
    import threading

    name = "test_concurrent_ops"
    assert perf.gauge_value(name) == 0

    peak = 0
    peak_lock = threading.Lock()
    start = threading.Barrier(5)
    release = threading.Event()

    def worker():
        start.wait()
        with perf.active_gauge(name):
            nonlocal peak
            with peak_lock:
                peak = max(peak, perf.gauge_value(name))
            release.wait(timeout=5)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    # Let all five enter the gauge before releasing them.
    while perf.gauge_value(name) < 5 and any(t.is_alive() for t in threads):
        pass
    release.set()
    for t in threads:
        t.join(timeout=5)

    assert peak == 5  # all five concurrent operations were counted at once
    assert perf.gauge_value(name) == 0  # the gauge returns to zero after each block


def test_active_gauge_decrements_on_exception():
    name = "test_gauge_error"
    with pytest.raises(ValueError):
        with perf.active_gauge(name):
            assert perf.gauge_value(name) == 1
            raise ValueError("boom")
    assert perf.gauge_value(name) == 0
