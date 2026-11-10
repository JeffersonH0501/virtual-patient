"""Join owned synchronous work before cancellation can close its resources."""
import asyncio
import logging
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


async def _join(task):
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    return task.result()


async def run_sync_owned(function, *args, **kwargs):
    """Use the existing bounded pool without abandoning work on task cancellation."""
    return await _join(asyncio.create_task(run_in_threadpool(function, *args, **kwargs)))


async def cancel_and_drain(task):
    if task is None:
        return
    task.cancel()
    try:
        await _join(task)
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():
            raise
    except Exception as error:
        logger.warning("Background cleanup failed: %s", type(error).__name__)
