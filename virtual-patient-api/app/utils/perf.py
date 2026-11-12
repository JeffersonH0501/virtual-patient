"""Lightweight, non-intrusive performance observability.

Emits the existing ``performance_event`` log convention
(``performance_event component=... operation=... phase=... key=value ...
duration_ms=... status=... trace_id=... worker_pid=... worker_rss_mb=...``) from a
single place so callers do not copy the ``perf_counter`` phase pattern by hand.

Design constraints (see the request that introduced this module):
- Reuse the existing text ``performance_event`` format and ``runtime_metrics``.
- Never block or raise into the measured operation: logging failures are swallowed.
- Never log media, transcripts, prompts, credentials or personal data. Callers
  pass only safe technical metadata (sizes, counts, durations, ids, status).
- Performance events are always enabled.
"""

from __future__ import annotations

import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Any, Iterator

from app.utils.runtime_metrics import current_rss_mb, process_id

logger = logging.getLogger("app.perf")

# Correlates frontend -> API -> worker. Set per request from the X-Trace-Id
# header (see app.core.trace) or passed explicitly to perf_event/track.
_current_trace_id: ContextVar[str | None] = ContextVar("perf_trace_id", default=None)
_event_store_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="interview-perf-store")


def set_trace_id(trace_id: str | None) -> None:
    """Bind the active trace id for the current context (request or task)."""
    _current_trace_id.set(trace_id or None)


def get_trace_id() -> str | None:
    """Return the trace id bound to the current context, if any."""
    return _current_trace_id.get()


def _format_value(value: Any) -> str:
    """Render one field value as a single space-free token for the log line."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    # Collapse whitespace so one event stays on one greppable line.
    return "_".join(str(value).split())


def perf_event(
    component: str,
    operation: str,
    *,
    phase: str = "complete",
    status: str = "success",
    duration_ms: float | None = None,
    trace_id: str | None = None,
    **fields: Any,
) -> None:
    """Emit one ``performance_event`` line. Never raises into the caller."""
    try:
        parts = [
            "performance_event",
            f"component={_format_value(component)}",
            f"operation={_format_value(operation)}",
            f"phase={_format_value(phase)}",
            f"status={_format_value(status)}",
            f"trace_id={_format_value(trace_id if trace_id is not None else get_trace_id())}",
        ]
        if duration_ms is not None:
            parts.append(f"duration_ms={duration_ms:.3f}")
        for key, value in fields.items():
            parts.append(f"{key}={_format_value(value)}")
        parts.append(f"worker_pid={process_id()}")
        parts.append(f"worker_rss_mb={_format_value(current_rss_mb())}")
        logger.info(" ".join(parts))
        interview_id = fields.get("interview_id")
        if isinstance(interview_id, str) and interview_id.isdecimal():
            interview_id = int(interview_id)
        if isinstance(interview_id, int):
            from app.utils.interview_performance import persist_interview_performance_event
            event = {
                "interview_id": interview_id,
                "created_at": datetime.now(timezone.utc),
                "component": component,
                "operation": operation,
                "phase": phase,
                "status": status,
                "duration_ms": duration_ms,
                "trace_id": trace_id if trace_id is not None else get_trace_id(),
                "fields": {key: value for key, value in fields.items() if key != "interview_id"},
            }
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                persist_interview_performance_event(**event)
            else:
                _event_store_executor.submit(persist_interview_performance_event, **event)
    except Exception:  # noqa: BLE001 - observability must never break a flow.
        pass


from collections import Counter
from threading import Lock

# Process-local gauges (e.g. concurrent P0 operations in this API worker). Not a
# cluster-wide count; with multiple API workers, sum across their logs. Cheap:
# an int map guarded by a lock, read into the event fields.
_gauges: Counter[str] = Counter()
_gauge_lock = Lock()


def gauge_value(name: str) -> int:
    with _gauge_lock:
        return _gauges[name]


@contextmanager
def active_gauge(name: str) -> Iterator[None]:
    """Count a concurrent operation for the duration of the block (process-local)."""
    with _gauge_lock:
        _gauges[name] += 1
    try:
        yield
    finally:
        with _gauge_lock:
            _gauges[name] -= 1


@contextmanager
def track(
    component: str,
    operation: str,
    *,
    trace_id: str | None = None,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Time a block with a monotonic clock and emit one ``performance_event``.

    Yields a mutable dict so the caller can attach late metadata (for example a
    produced count) that is included in the final event::

        with track("speech", "stt", audio_ms=1200) as event:
            result = transcribe(...)
            event["chars"] = len(result.text)

    On success emits ``phase=complete status=success``; on exception emits
    ``phase=error status=error error_type=<ExceptionClass>`` and re-raises, so
    the measured operation's behavior is unchanged.
    """
    extra: dict[str, Any] = dict(fields)
    started = perf_counter()
    try:
        yield extra
    except BaseException as error:  # noqa: BLE001 - record then re-raise unchanged.
        perf_event(
            component, operation, phase="error", status="error",
            duration_ms=(perf_counter() - started) * 1000,
            trace_id=trace_id, error_type=type(error).__name__, **extra,
        )
        raise
    else:
        perf_event(
            component, operation, phase="complete", status="success",
            duration_ms=(perf_counter() - started) * 1000,
            trace_id=trace_id, **extra,
        )
