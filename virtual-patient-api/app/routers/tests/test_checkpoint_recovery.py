"""Recover checkpointed replies when the canonical exchange transaction fails."""
import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import psycopg
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, MessagesState, START, END
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import SQLALCHEMY_DATABASE_URL

from app.agents.virtual_patient_agent import VirtualPatientAgent
from app.agents.virtual_patient_workflow import VirtualPatientWorkflow
from app.routers import interview_messages as messages
from app.routers.tests.test_lifecycle_integrity import lifecycle_api, start_capture


@pytest.mark.parametrize("history, expected_opening", [
    ([], False),
    ([{"role": "assistant", "content": "Synthetic greeting"}], True),
    ([{"role": "assistant", "content": "Synthetic greeting"},
      {"role": "user", "content": "Earlier question"},
      {"role": "assistant", "content": "Earlier response"}], False),
])
def test_controller_seeds_opening_only_for_the_first_student_turn(monkeypatch, history, expected_opening):
    from app.controllers import virtual_patient_controller as module
    workflow = SimpleNamespace(process_interview_message=AsyncMock(return_value={}))
    resources = SimpleNamespace(from_conn_string=lambda *args, **kwargs: nullcontext(object()))
    monkeypatch.setattr(module, "PostgresStore", resources)
    monkeypatch.setattr(module, "PostgresSaver", resources)
    monkeypatch.setattr(module, "create_virtual_patient_workflow", lambda **kwargs: workflow)
    question = {"role": "user", "content": "Synthetic question"}
    asyncio.run(module.VirtualPatientController().process_interview_message(7, [*history, question], None))
    arguments = workflow.process_interview_message.call_args.kwargs
    assert arguments["question"] == question
    assert arguments["history"] == ([AIMessage(content="Synthetic greeting", id="opening-7")] if expected_opening else [])


@pytest.fixture
def checkpoint_workflow(monkeypatch, lifecycle_api):
    import app.agents.virtual_patient_agent as agent_module
    generate = AsyncMock(return_value=None)
    calls = []
    def respond(state):
        calls.append(state["messages"][-1].content)
        return {"messages": [AIMessage(content="Synthetic base response")]}
    graph = StateGraph(MessagesState)
    graph.add_node("model", respond)
    graph.add_edge(START, "model")
    graph.add_edge("model", END)
    agent = object.__new__(VirtualPatientAgent)
    agent.interview_id = "synthetic-checkpoint"
    agent.persist_background_memory = True
    with Session(lifecycle_api.engine) as db:
        schema = db.scalar(text("SELECT current_schema()"))
    connection = psycopg.connect(SQLALCHEMY_DATABASE_URL, autocommit=True,
        options=f"-csearch_path={schema}")
    saver = PostgresSaver(connection)
    saver.setup()
    agent.hot_path_agent = graph.compile(checkpointer=saver)
    monkeypatch.setattr(agent_module, "process_background_memories_standalone", generate)
    workflow = object.__new__(VirtualPatientWorkflow)
    workflow.interview_id = agent.interview_id
    workflow.agent = agent
    workflow.patient_gender = workflow.patient_name = None
    workflow.current_language = "English"
    workflow.personality = "synthetic"
    workflow.translator_agent = SimpleNamespace(translate_patient_with_personality=AsyncMock(return_value="Synthetic final response"))
    workflow.workflow = workflow._create_workflow()
    try:
        yield workflow, calls
    finally:
        connection.close()


def test_checkpointed_reply_survives_exchange_commit_failure(lifecycle_api, checkpoint_workflow, monkeypatch):
    state = lifecycle_api
    start_capture(state)
    workflow, generated = checkpoint_workflow
    async def process(**kwargs):
        result = await workflow.process_interview_message(
            question={"role": "user", "content": kwargs["user_message_content"]},
            clinical_case=None, thread_id="synthetic-checkpoint",
            client_request_id=kwargs["message_metadata"]["client_request_id"])
        return {"agent_response": result["interview_result"]["messages"][-1].content,
            "agent_message_object": SimpleNamespace(message_metadata={}),
            "user_message_object": SimpleNamespace(content=kwargs["user_message_content"], message_metadata={})}
    monkeypatch.setattr(messages, "VirtualPatientController", lambda: SimpleNamespace(process_user_message=process))
    monkeypatch.setattr(messages, "persist_patient_audio", lambda *_: SimpleNamespace(synthesis_metadata={}, audio_url=None))
    persist = messages._create_exchange_messages
    attempts = []
    def fail_once(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("Synthetic database failure after checkpoint commit")
        return persist(*args, **kwargs)
    monkeypatch.setattr(messages, "_create_exchange_messages", fail_once)
    payload = {"content": "Synthetic checkpoint question", "client_request_id": str(uuid4())}
    assert state.client.post(f"/medical-interviews/{state.id}/messages", json=payload).status_code == 500
    retry = state.client.post(f"/medical-interviews/{state.id}/messages", json=payload)
    assert retry.status_code == 200
    assert len(retry.json()["messages"]) == 3
    assert retry.json()["messages"][-1]["content"] == "Synthetic final response"
    assert generated == [payload["content"]]
    workflow.translator_agent.translate_patient_with_personality.assert_awaited_once()


def test_pending_checkpoint_resumes_without_appending_the_question(checkpoint_workflow):
    workflow, generated = checkpoint_workflow
    request_id = str(uuid4())
    graph = workflow.agent.hot_path_agent
    config = {"configurable": {"thread_id": "pending-synthetic"}}
    graph.update_state(config, {"messages": [HumanMessage(content="Synthetic pending question", id=f"client-request-{request_id}")]}, as_node="__start__")
    result = asyncio.run(workflow.process_interview_message(
        question={"content": "Synthetic pending question"}, clinical_case=None,
        thread_id="pending-synthetic", client_request_id=request_id))
    assert generated == ["Synthetic pending question"]
    saved = graph.get_state(config).values["messages"]
    assert len([message for message in saved if isinstance(message, HumanMessage)]) == 1
    assert result["interview_result"]["messages"][-1].content == "Synthetic final response"


def test_rewrite_failure_preserves_original_checkpoint_and_same_request_recovery(lifecycle_api, checkpoint_workflow, monkeypatch):
    from app.agents.translator_agent import TranslatorAgent
    from app.models.medical_interview import InterviewMessageDB, InterviewTurnDB
    state = lifecycle_api
    start_capture(state)
    workflow, generated = checkpoint_workflow
    workflow.current_language = 'Spanish'
    workflow.personality = 'friendly_polite'
    workflow.patient_gender = 'female'
    workflow.patient_name = 'Synthetic'
    translator = TranslatorAgent()
    model = AsyncMock(side_effect=[RuntimeError('Synthetic rewrite failure'), SimpleNamespace(content='Synthetic final response')])
    translator.llm_personality = SimpleNamespace(ainvoke=model)
    workflow.translator_agent = translator
    async def process(**kwargs):
        result = await workflow.process_interview_message(
            question={'role': 'user', 'content': kwargs['user_message_content']}, clinical_case=None,
            thread_id='synthetic-checkpoint', client_request_id=kwargs['message_metadata']['client_request_id'])
        return {'agent_response': result['interview_result']['messages'][-1].content,
            'agent_message_object': SimpleNamespace(message_metadata={}),
            'user_message_object': SimpleNamespace(content=kwargs['user_message_content'], message_metadata={})}
    monkeypatch.setattr(messages, 'VirtualPatientController', lambda: SimpleNamespace(process_user_message=process))
    from unittest.mock import Mock
    audio_metadata = Mock(return_value=SimpleNamespace(synthesis_metadata={}, audio_url=None))
    monkeypatch.setattr(messages, 'persist_patient_audio', audio_metadata)
    payload = {'content': 'Synthetic recoverable question', 'client_request_id': str(uuid4())}
    failed = state.client.post(f'/medical-interviews/{state.id}/messages', json=payload)
    assert failed.status_code == 500
    audio_metadata.assert_not_called()
    with Session(state.engine) as db:
        history = db.query(InterviewMessageDB).filter_by(interview_id=state.id).all()
        assert len(history) == 1
        assert history[0].message_metadata.get('opening') is True
        assert db.query(InterviewTurnDB).count() == 0
    saved = workflow.agent.hot_path_agent.get_state({'configurable': {'thread_id': 'synthetic-checkpoint'}}).values['messages']
    assert saved[-1].content == 'Synthetic base response'
    assert 'finalized_client_request_id' not in saved[-1].additional_kwargs
    retry = state.client.post(f'/medical-interviews/{state.id}/messages', json=payload)
    assert retry.status_code == 200
    assert retry.json()['messages'][-1]['content'] == 'Synthetic final response'
    assert generated == [payload['content']]
    assert model.await_count == 2
    repeated = state.client.post(f'/medical-interviews/{state.id}/messages', json=payload)
    assert repeated.json()['new_message_ids'] == retry.json()['new_message_ids']
    assert model.await_count == 2


def test_rewrite_failure_drains_owned_background_before_return(checkpoint_workflow, monkeypatch):
    from app.agents.translator_agent import PatientResponseError
    import app.agents.virtual_patient_agent as agent_module
    workflow, _ = checkpoint_workflow
    stopped = []
    async def scenario():
        started = asyncio.Event()
        async def background(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.01)
                stopped.append(True)
        async def rewrite(**kwargs):
            await started.wait()
            raise PatientResponseError('Synthetic failure')
        monkeypatch.setattr(agent_module, 'process_background_memories_standalone', background)
        workflow.translator_agent.translate_patient_with_personality = rewrite
        with pytest.raises(PatientResponseError):
            await workflow.process_interview_message({'content':'Synthetic failed turn'},None,
                thread_id='synthetic-failed-background',client_request_id=str(uuid4()))
        assert stopped == [True]
        assert workflow.agent.background_task.done()
    asyncio.run(scenario())


def test_controller_postprocessing_failure_drains_background(lifecycle_api, monkeypatch):
    import app.controllers.virtual_patient_controller as controller_module
    from app.controllers.medical_interview_controller import MedicalInterviewController
    state = lifecycle_api
    start_capture(state)
    stopped = []
    async def process(self, **kwargs):
        async def background():
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.01)
                stopped.append(True)
        task = asyncio.create_task(background())
        await asyncio.sleep(0)
        return {'interview_result':{'messages':[AIMessage(content='Synthetic final response')]},'_background_task':task}
    monkeypatch.setattr(controller_module.VirtualPatientController,'process_interview_message',process)
    def fail(*args,**kwargs):
        raise RuntimeError('Synthetic postprocessing failure')
    monkeypatch.setattr(MedicalInterviewController,'create_agent_message_object',fail)
    response=state.client.post(f'/medical-interviews/{state.id}/messages',json={
        'content':'Synthetic question','client_request_id':str(uuid4())})
    assert response.status_code==500
    assert stopped==[True]
