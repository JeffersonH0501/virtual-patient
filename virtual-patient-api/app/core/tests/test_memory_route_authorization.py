"""Real route authorization and store access; only the LLM workflow is synthetic."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.tests.test_memory_namespace_isolation import database, embeddings
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.memory_store import PostgresStore
from app.models.organization import OrganizationDB
from app.models.user import UserDB, UserRole
from app.models.clinical_case import ClinicalCaseDB
from app.models.medical_interview import MedicalInterviewDB, InterviewStatus
from app.routers import interview_messages
from app.controllers import virtual_patient_controller


@pytest.fixture
def route_api(database, monkeypatch):
    engine = create_engine(settings.database_url,
        connect_args={'options': f'-c search_path={database.schema},public'},
        execution_options={'schema_translate_map': {None: database.schema}})
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='medical_interviews'::regclass")) == database.schema
    with Session(engine, expire_on_commit=False) as session:
        organizations = [OrganizationDB(name='Synthetic organization '+str(i), active=True) for i in range(2)]
        session.add_all(organizations)
        session.flush()
        users = [UserDB(name='Synthetic user', email=uuid4().hex+'@example.invalid',
            hashed_password='unused-synthetic', role=UserRole.STUDENT,
            organization_id=organizations[0 if index < 2 else 1].id) for index in range(3)]
        session.add_all(users)
        case = ClinicalCaseDB(title='Synthetic case', description='Synthetic case only')
        session.add(case)
        session.flush()
        for identifier, owner in zip((1, 12, 123), users):
            session.add(MedicalInterviewDB(id=identifier, user_id=owner.id, clinical_case_id=case.id,
                status=InterviewStatus.IN_PROGRESS, start_time=datetime.now(timezone.utc)))
        session.commit()
    with database() as connection:
        store = PostgresStore(connection, index={'dims': 2, 'embed': embeddings, 'fields': ['text']})
        store.setup()
        for identifier in (1, 12, 123):
            store.put(('semantic_memory_store', str(identifier)), 'fixture', {'text': 'synthetic '+str(identifier)})
    dsn = make_conninfo(settings.database_url, options=f'-c search_path={database.schema},public')
    monkeypatch.setattr(virtual_patient_controller, 'SQLALCHEMY_DATABASE_URL', dsn)
    monkeypatch.setattr(virtual_patient_controller, 'embeddings', embeddings)
    monkeypatch.setattr(virtual_patient_controller, 'EMBEDDING_DIMENSIONS', 2)
    calls = []
    def workflow_factory(*, store, interview_id, **kwargs):
        async def process(**kwargs):
            namespace = ('semantic_memory_store', interview_id)
            memories = store.search(namespace, query='synthetic', limit=1)
            assert [item.namespace for item in memories] == [namespace]
            assert memories[0].value == {'text': 'synthetic '+interview_id}
            store.put(namespace, 'route-write', {'text': 'authorized synthetic write'})
            calls.append(interview_id)
            return {'interview_result': {'messages': [{'content': 'Synthetic response '+interview_id}]}}
        return SimpleNamespace(process_interview_message=process)
    monkeypatch.setattr(virtual_patient_controller, 'create_virtual_patient_workflow', workflow_factory)
    app = FastAPI()
    app.include_router(interview_messages.router)
    actor = [users[0]]
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_active_user] = lambda: actor[0]
    try:
        with TestClient(app) as client:
            yield client, actor, users, calls, database, app
    finally:
        engine.dispose()


@pytest.mark.parametrize('actor_index', [0, 1, 2])
@pytest.mark.parametrize('target', [1, 12, 123])
def test_user_and_organization_authorization_precedes_memory_access(route_api, actor_index, target):
    client, actor, users, calls, database, _ = route_api
    actor[0] = users[actor_index]
    own = (1, 12, 123)[actor_index] == target
    read = client.get(f'/medical-interviews/{target}/messages')
    assert read.status_code == (200 if own else 403), read.text
    identifier = str(uuid4())
    payload = {'content': 'Synthetic question', 'client_request_id': identifier}
    response = client.post(f'/medical-interviews/{target}/messages', json=payload)
    assert response.status_code == (200 if own else 404), response.text
    if own:
        retry = client.post(f'/medical-interviews/{target}/messages', json=payload)
        assert retry.status_code == 200
        assert retry.json()['new_message_ids'] == response.json()['new_message_ids']
        assert calls == [str(target)]
    else:
        assert calls == []
        with database() as connection:
            assert PostgresStore(connection).get(('semantic_memory_store', str(target)), 'route-write') is None


def test_unauthenticated_requests_never_reach_memory(route_api):
    client, _, _, calls, _, app = route_api
    del app.dependency_overrides[get_current_active_user]
    assert client.get('/medical-interviews/1/messages').status_code == 401
    assert client.post('/medical-interviews/1/messages', json={'content': 'Synthetic question'}).status_code == 401
    assert calls == []
