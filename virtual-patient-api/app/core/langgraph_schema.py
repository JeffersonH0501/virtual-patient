"""Idempotent database bootstrap for LangGraph persistence."""

from psycopg import Connection
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from app.core.azure_openai import EMBEDDING_DIMENSIONS
from app.core.config import settings


def _schema_embeddings(texts: list[str]) -> list[list[float]]:
    """Provide correctly sized vectors without contacting an external provider."""
    return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]


def ensure_langgraph_schema(database_url: str | None = None) -> str:
    """Create or migrate LangGraph store and checkpoint tables."""
    connection_url = database_url or settings.database_url

    with Connection.connect(connection_url, autocommit=True) as connection:
        store = PostgresStore(
            conn=connection,
            index={
                "dims": EMBEDDING_DIMENSIONS,
                "embed": _schema_embeddings,
            },
        )
        checkpointer = PostgresSaver(conn=connection)
        store.setup()
        checkpointer.setup()

    return "Prepared LangGraph store and checkpoint tables"
