"""Protect synchronous graph lifetime while keeping the request loop available."""
import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from app.agents import virtual_patient_agent as module


def make_pending_agent(monkeypatch):
    entered, release, finished, closed = Event(), Event(), Event(), Event()
    background = AsyncMock()
    monkeypatch.setattr(module, 'process_background_memories_standalone', background)
    def invoke(*args, **kwargs):
        entered.set()
        if not release.wait(1):
            raise TimeoutError('The event loop could not release its synthetic provider')
        assert not closed.is_set(), 'Resource closed before the synchronous invocation ended'
        finished.set()
        return {'messages': [AIMessage(content='Synthetic response')]}
    agent = object.__new__(module.VirtualPatientAgent)
    agent.persist_background_memory = True
    agent.interview_id = 'synthetic'
    agent.hot_path_agent = SimpleNamespace(invoke=invoke)
    async def request():
        try:
            return await agent.process_medical_interview_message([{'content':'Synthetic question'}],None)
        finally:
            closed.set()
    return request, entered, release, finished, closed, background


def test_pending_graph_keeps_event_loop_available(monkeypatch):
    request, entered, release, finished, closed, _ = make_pending_agent(monkeypatch)
    async def scenario():
        pending=asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(entered.wait,2)
            assert not pending.done()
        finally:
            release.set()
            await pending
        assert finished.is_set() and closed.is_set()
    asyncio.run(scenario())


def test_native_cancellation_waits_for_graph_before_closing_resources(monkeypatch):
    request, entered, release, finished, closed, background = make_pending_agent(monkeypatch)
    async def scenario():
        pending=asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(entered.wait,2)
            pending.cancel()
            await asyncio.sleep(.02)
            pending.cancel()  # Repeated ASGI/task cancellation must not abandon a thread.
            await asyncio.sleep(.02)
            assert not pending.done() and not closed.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
        assert finished.is_set() and closed.is_set()
        background.assert_not_called()
    asyncio.run(scenario())


def test_five_concurrent_postgres_agents_keep_checkpoints_and_memory_separate(database, monkeypatch):
    from contextlib import ExitStack
    from uuid import uuid4
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.checkpoint.postgres import PostgresSaver
    from app.core.memory_store import PostgresStore
    monkeypatch.setattr(module, 'process_background_memories_standalone', AsyncMock())
    calls=[]
    with ExitStack() as stack:
        agents=[]
        for identifier in ('1','12','123','2','3'):
            connection=stack.enter_context(database())
            store=PostgresStore(connection); store.setup()
            checkpoint_connection=stack.enter_context(database())
            saver=PostgresSaver(checkpoint_connection); saver.setup()
            def respond(state, identifier=identifier, memory_store=store):
                calls.append(identifier)
                namespace=('semantic_memory_store',identifier)
                memory_store.put(namespace,'fixture',{'synthetic':identifier})
                assert all(item.namespace==namespace for item in memory_store.search(namespace))
                return {'messages':[AIMessage(content='Synthetic response '+identifier)]}
            graph=StateGraph(MessagesState)
            graph.add_node('model',respond); graph.add_edge(START,'model'); graph.add_edge('model',END)
            agent=object.__new__(module.VirtualPatientAgent)
            agent.persist_background_memory = True
            agent.interview_id=identifier
            agent.hot_path_agent=graph.compile(checkpointer=saver,store=store)
            agents.append((agent,str(uuid4())))
        async def scenario():
            async def request(agent,key):
                return await agent.process_medical_interview_message([{'role':'user','content':'Synthetic question'}],None,
                    thread_id=agent.interview_id,client_request_id=key)
            first=await asyncio.gather(*(request(agent,key) for agent,key in agents))
            retry=await asyncio.gather(*(request(agent,key) for agent,key in agents))
            assert len(calls)==5
            for (agent,_), result, recovered in zip(agents,first,retry):
                assert len(result['messages'])==len(recovered['messages'])==2
                assert recovered['messages'][-1].content=='Synthetic response '+agent.interview_id
        asyncio.run(scenario())


from app.core.tests.test_memory_namespace_isolation import database
