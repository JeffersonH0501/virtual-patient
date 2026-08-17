"""Unit tests for LangGraph database schema bootstrap."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.core import langgraph_schema


class LangGraphSchemaTests(TestCase):
    """Verify that both persistence components are initialized safely."""

    @patch.object(langgraph_schema, "PostgresSaver")
    @patch.object(langgraph_schema, "PostgresStore")
    @patch.object(langgraph_schema.Connection, "connect")
    def test_ensure_langgraph_schema_initializes_store_and_checkpointer(
        self,
        connect: MagicMock,
        store_class: MagicMock,
        saver_class: MagicMock,
    ) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection

        result = langgraph_schema.ensure_langgraph_schema(
            "postgresql://user:password@database/example"
        )

        connect.assert_called_once_with(
            "postgresql://user:password@database/example",
            autocommit=True,
        )
        store_class.assert_called_once()
        store_arguments = store_class.call_args.kwargs
        self.assertIs(store_arguments["conn"], connection)
        self.assertEqual(
            store_arguments["index"]["dims"],
            langgraph_schema.EMBEDDING_DIMENSIONS,
        )
        self.assertTrue(callable(store_arguments["index"]["embed"]))
        store_class.return_value.setup.assert_called_once_with()
        saver_class.assert_called_once_with(conn=connection)
        saver_class.return_value.setup.assert_called_once_with()
        self.assertEqual(
            result,
            "Prepared LangGraph store and checkpoint tables",
        )

    def test_schema_embeddings_do_not_contact_external_services(self) -> None:
        vectors = langgraph_schema._schema_embeddings(["first", "second"])

        self.assertEqual(len(vectors), 2)
        self.assertTrue(
            all(
                len(vector) == langgraph_schema.EMBEDDING_DIMENSIONS
                for vector in vectors
            )
        )
        self.assertTrue(all(value == 0.0 for vector in vectors for value in vector))
