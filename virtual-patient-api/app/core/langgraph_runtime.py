"""Shared, pooled LangGraph store and checkpointer.

Each patient turn used to open (and tear down) a fresh PostgreSQL connection via
``from_conn_string`` for the memory store, the checkpointer and the background
memory task. That added connection setup to the interactive path and opened
connections outside the SQLAlchemy pool, risking ``too many connections`` under
concurrent interviews plus the worker and child processes.

This module owns one bounded ``ConnectionPool`` for LangGraph persistence,
created lazily per process. Each turn borrows a connection from the pool and
constructs the store/checkpointer on it, so turns no longer pay connection setup
and total connections stay bounded. The schema is prepared once elsewhere
(``ensure_langgraph_schema``); ``.setup()`` is not run per turn.
"""

from contextlib import contextmanager
from threading import Lock

from psycopg_pool import ConnectionPool

from app.core.azure_openai import EMBEDDING_DIMENSIONS as _DEFAULT_DIMS, create_embeddings
from app.core.config import settings
from app.core.memory_store import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver

# Module-level so tests can redirect persistence to a schema-scoped database.
DATABASE_URL = settings.database_url
EMBEDDING_DIMENSIONS = _DEFAULT_DIMS

# A bounded pool dedicated to LangGraph persistence, separate from the
# SQLAlchemy pool. A turn borrows two connections (store and checkpointer) and its background
# memory task a third, so this must exceed three per concurrent turn while the aggregate across
# processes still stays within
# PostgreSQL max_connections.
_POOL_MAX_SIZE = 12

_pool: ConnectionPool | None = None
_pool_lock = Lock()
_embeddings = None


def _get_pool() -> ConnectionPool:
    global _pool, _embeddings
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if _embeddings is None:
                    _embeddings = create_embeddings()
                _pool = ConnectionPool(
                    conninfo=DATABASE_URL,
                    max_size=_POOL_MAX_SIZE,
                    kwargs={"autocommit": True},
                    open=True,
                )
    return _pool


def _index_config():
    return {"dims": EMBEDDING_DIMENSIONS, "embed": _embeddings}


@contextmanager
def langgraph_store():
    """Borrow a pooled connection and yield a memory store bound to it."""
    pool = _get_pool()
    with pool.connection() as connection:
        yield PostgresStore(conn=connection, index=_index_config())


@contextmanager
def langgraph_store_and_checkpointer():
    """Borrow two pooled connections: one for the store and one for the checkpointer.

    The store and the checkpointer each serialize their own use with a lock, but they do not share it.
    Running both on one connection let a checkpoint write overlap a memory read and corrupted the
    connection ("another command is already in progress"), which failed the turn.
    """
    pool = _get_pool()
    with pool.connection() as store_connection, pool.connection() as checkpoint_connection:
        yield PostgresStore(conn=store_connection, index=_index_config()), PostgresSaver(conn=checkpoint_connection)

def close_langgraph_pool() -> None:
    """Close the pool on shutdown; safe to call when it was never opened."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
