"""A patient turn must not run its store and its checkpointer on the same connection."""
from contextlib import contextmanager
from unittest.mock import patch

from app.core import langgraph_runtime


class FakePool:
    def __init__(self):
        self.borrowed = []
        self.active = 0
        self.peak = 0

    @contextmanager
    def connection(self):
        connection = object()
        self.borrowed.append(connection)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            yield connection
        finally:
            self.active -= 1


def test_store_and_checkpointer_use_different_pooled_connections():
    pool = FakePool()
    with patch.object(langgraph_runtime, "_get_pool", return_value=pool), \
            patch.object(langgraph_runtime, "PostgresStore") as store_class, \
            patch.object(langgraph_runtime, "PostgresSaver") as saver_class, \
            patch.object(langgraph_runtime, "_index_config", return_value={}):
        with langgraph_runtime.langgraph_store_and_checkpointer() as (store, checkpointer):
            assert pool.active == 2
            assert store is store_class.return_value and checkpointer is saver_class.return_value
    store_connection = store_class.call_args.kwargs["conn"]
    checkpoint_connection = saver_class.call_args.kwargs["conn"]
    assert store_connection is not checkpoint_connection
    assert pool.active == 0 and pool.peak == 2


def test_pool_leaves_room_for_the_background_memory_task_of_concurrent_turns():
    # Two connections per turn plus one for its background memory task.
    assert langgraph_runtime._POOL_MAX_SIZE >= 3 * 3
