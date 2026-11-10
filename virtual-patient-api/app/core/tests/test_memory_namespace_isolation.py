"""Real PostgreSQL regressions using only disposable synthetic namespaces."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from psycopg import Connection, sql
from psycopg.rows import dict_row
from langgraph.store.postgres import PostgresStore as OriginalStore
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.store.base import GetOp, PutOp, SearchOp

from app.core.config import settings
from app.controllers.virtual_patient_controller import PostgresStore
from app.agents.enhanced_memory_manager import SemanticMemory


@pytest.fixture
def database():
    schema = 'c23_test_' + uuid4().hex
    assert len(schema) == 41 and schema.startswith('c23_test_')
    with Connection.connect(settings.database_url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            def connect():
                return Connection.connect(settings.database_url, autocommit=True,
                    row_factory=dict_row, options=f'-c search_path={schema},public')
            connect.schema = schema
            yield connect
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def embeddings(texts):
    return [[1.0, 0.0] if text != 'distant' else [0.0, 1.0] for text in texts]


@pytest.fixture
def store(database):
    with database() as connection:
        result = PostgresStore(connection, index={'dims': 2, 'embed': embeddings, 'fields': ['text']})
        result.setup()
        assert connection.execute("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='store'::regclass").fetchone()['nspname'] == database.schema
        yield result


@pytest.mark.parametrize('requested,other', [
    ('1', '12'), ('12', '1'), ('12', '123'), ('session', 'session_extra'),
    ('user_1', 'userX1'), ('user%1', 'userXYZ1'), ('a\\b', 'ab'),
    ('a[1]', 'a1'), ('a|b', 'b'),
])
@pytest.mark.parametrize('vector', [False, True])
def test_namespace_filter_precedes_ranking_and_limit(store, requested, other, vector):
    own = ('semantic_memory_store', requested)
    alien = ('semantic_memory_store', other)
    store.put(own, 'own', {'text': 'distant', 'kind': 'synthetic'})
    for index in range(4):
        store.put(alien, str(index), {'text': 'nearest', 'kind': 'synthetic'})
    results = store.search(own, query='nearest' if vector else None,
                           filter={'kind': 'synthetic'}, limit=1)
    assert [(item.namespace, item.key) for item in results] == [(own, 'own')]
    assert store.search(own, query='nearest' if vector else None, offset=1) == []


def test_hierarchy_and_listing_match_segments(store):
    namespaces = [('family', '1'), ('family', '1', 'child'), ('family', '12'),
                  ('familyX', '1'), ('family', 'user_1'), ('family', 'userX1')]
    for namespace in namespaces:
        store.put(namespace, 'fixture', {'synthetic': True})
    assert {item.namespace for item in store.search(('family', '1'))} == set(namespaces[:2])
    assert set(store.list_namespaces(prefix=('family', '1'))) == set(namespaces[:2])
    assert set(store.list_namespaces(suffix=('1',))) == {namespaces[0], namespaces[3]}
    assert set(store.list_namespaces(prefix=('family', 'user_1'))) == {namespaces[4]}
    assert set(store.list_namespaces(prefix=('family', '*'), suffix=('child',))) == {namespaces[1]}


@pytest.mark.parametrize('operation', ['get', 'put', 'search', 'list', 'batch'])
def test_ambiguous_namespace_labels_are_rejected_before_sql(store, operation):
    store.put(('family', '1'), 'fixture', {'synthetic': True})
    with pytest.raises(ValueError):
        if operation == 'get':
            store.get(('family.1',), 'fixture')
        elif operation == 'put':
            store.put(('family.1',), 'fixture', {'synthetic': True})
        elif operation == 'search':
            store.search(('family.1',))
        elif operation == 'list':
            store.list_namespaces(prefix=('family.1',))
        else:
            store.batch([GetOp(('family.1',), 'fixture')])


def test_async_batch_ttl_retry_and_missing_memory(store):
    namespace = ('semantic_background_memory_store', '1')
    store.put(namespace, 'stable', {'synthetic': True}, ttl=60)
    store.put(('semantic_background_memory_store', '12'), 'alien', {'synthetic': True}, ttl=60)
    async def scenario():
        for _ in range(2):
            results = await store.abatch([
                PutOp(namespace, 'stable', {'synthetic': True}),
                GetOp(namespace, 'stable'), SearchOp(namespace, limit=1, refresh_ttl=True),
            ])
            assert results[1].value == {'synthetic': True}
            assert [item.namespace for item in results[2]] == [namespace]
        assert await store.asearch(('semantic_background_memory_store', '999')) == []
    asyncio.run(scenario())


def test_existing_memories_and_checkpoints_remain_readable(database):
    with database() as connection:
        old = OriginalStore(connection)
        old.setup()
        old.put(('semantic_memory_store', '1'), 'legacy', {'synthetic': True})
        saver = PostgresSaver(connection)
        saver.setup()
        checkpoint = empty_checkpoint()
        checkpoint['channel_values'] = {'synthetic': 'old checkpoint'}
        saved = saver.put({'configurable': {'thread_id': 'interview-1', 'checkpoint_ns': ''}}, checkpoint, {}, {})
    with database() as connection:
        current = PostgresStore(connection)
        assert current.get(('semantic_memory_store', '1'), 'legacy').value == {'synthetic': True}
        assert current.search(('semantic_memory_store', '1'))[0].key == 'legacy'
        saver = PostgresSaver(connection)
        assert saver.get(saved)['channel_values'] == {'synthetic': 'old checkpoint'}
        assert saver.get({'configurable': {'thread_id': 'interview-12'}}) is None


def test_real_semantic_tool_and_concurrent_sessions(database, store):
    store.put(('semantic_memory_store', '1'), 'own', {'text': 'distant'})
    store.put(('semantic_memory_store', '12'), 'alien', {'text': 'nearest'})
    def read(identifier):
        with database() as connection:
            scoped = PostgresStore(connection, index={'dims': 2, 'embed': embeddings, 'fields': ['text']})
            memory = SemanticMemory(scoped, identifier)
            result = memory.search_facts('nearest', limit=1)
            tool_result = memory.search_tool.invoke({'query': 'nearest', 'limit': 1})
            assert 'alien' not in str(tool_result) if identifier == '1' else 'own' not in str(tool_result)
            return [item.namespace for item in result]
    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = ['1', '12'] * 4
        assert list(pool.map(read, identifiers)) == [[('semantic_memory_store', item)] for item in identifiers]


def test_real_background_memory_retrieval(store):
    from app.agents.enhanced_memory_manager import EnhancedMemoryManager
    from app.agents.virtual_patient_agent import llm
    store.put(('semantic_background_memory_store', '1'), 'own', {'content': 'own synthetic memory', 'text': 'distant'})
    store.put(('semantic_background_memory_store', '12'), 'alien', {'content': 'alien synthetic memory', 'text': 'nearest'})
    manager = EnhancedMemoryManager(store, '1', llm=llm)
    result = manager.get_contextual_memory('nearest', limit=1)
    assert 'own synthetic memory' in str(result)
    assert 'alien synthetic memory' not in str(result)


def test_all_production_store_consumers_use_the_shared_boundary():
    from pathlib import Path
    from app.core.memory_store import PostgresStore as SafeStore
    from app.controllers import virtual_patient_controller, summary_controller
    from app.agents import virtual_patient_agent
    from app.core import langgraph_schema
    assert all(module.PostgresStore is SafeStore for module in (
        virtual_patient_controller, summary_controller, virtual_patient_agent, langgraph_schema))
    root = Path(__file__).resolve().parents[3]
    for folder in ('app', 'scripts'):
        for path in (root / folder).rglob('*.py'):
            if 'tests' in path.parts or path.name == 'memory_store.py':
                continue
            assert 'from langgraph.store.postgres import PostgresStore' not in path.read_text(), path


def test_resuming_original_graph_checkpoint_with_corrected_store(database):
    from langgraph.graph import StateGraph, START, END
    from typing_extensions import TypedDict
    class State(TypedDict):
        count: int
    def graph(store, saver):
        builder = StateGraph(State)
        builder.add_node('increment', lambda state: {'count': state['count'] + 1})
        builder.add_edge(START, 'increment')
        builder.add_edge('increment', END)
        return builder.compile(store=store, checkpointer=saver, interrupt_before=['increment'])
    config = {'configurable': {'thread_id': 'interview-1'}}
    with database() as connection:
        old = OriginalStore(connection)
        old.setup()
        saver = PostgresSaver(connection)
        saver.setup()
        original = graph(old, saver)
        original.invoke({'count': 7}, config)
        assert original.get_state(config).next == ('increment',)
    with database() as connection:
        corrected = graph(PostgresStore(connection), PostgresSaver(connection))
        assert corrected.invoke(None, config) == {'count': 8}
        assert corrected.get_state(config).next == ()


def test_query_shape_changes_fail_closed(store, monkeypatch):
    monkeypatch.setattr(OriginalStore, '_prepare_batch_search_queries',
        lambda self, ops: ([('SELECT 1', [])], []))
    with pytest.raises(RuntimeError, match='query shape'):
        store.search(('semantic_memory_store', '1'))
