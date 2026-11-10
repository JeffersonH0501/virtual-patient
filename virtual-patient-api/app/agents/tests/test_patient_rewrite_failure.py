"""Patient rewrite failures must remain technical, recoverable failures."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from app.agents.translator_agent import TranslatorAgent
from app.agents.virtual_patient_workflow import VirtualPatientWorkflow


@pytest.mark.parametrize('result', [RuntimeError('Synthetic provider failure'), '   '])
def test_patient_rewriter_raises_instead_of_returning_error_or_empty_text(result):
    translator = TranslatorAgent()
    response = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=SimpleNamespace(content=result))
    translator.llm_personality = SimpleNamespace(ainvoke=response)
    with pytest.raises(RuntimeError, match='Patient response rewriting failed'):
        asyncio.run(translator.translate_patient_with_personality(
            'Synthetic clinical response', 'Spanish', 'friendly_polite', 'female', 'Synthetic', []))


@pytest.mark.parametrize('language', ['English', 'Spanish'])
def test_workflow_does_not_replace_a_failed_rewrite_with_the_base_response(language):
    workflow = object.__new__(VirtualPatientWorkflow)
    workflow.current_language = language
    workflow.personality = 'friendly_polite'
    workflow.patient_gender = workflow.patient_name = None
    workflow.translator_agent = SimpleNamespace(translate_patient_with_personality=AsyncMock(side_effect=RuntimeError('Synthetic rewrite failure')))
    original = AIMessage(content='Synthetic original checkpoint response')
    state = {'interview_result': {'messages': [original]}}
    with pytest.raises(RuntimeError):
        asyncio.run(workflow.translate_patient_response_node(state))
    assert original.content == 'Synthetic original checkpoint response'
    assert 'finalized_client_request_id' not in original.additional_kwargs


@pytest.mark.parametrize('node', ['translate_patient_response_node', 'finalize_node'])
def test_workflow_error_state_never_becomes_patient_content(node):
    workflow = object.__new__(VirtualPatientWorkflow)
    with pytest.raises(RuntimeError):
        asyncio.run(getattr(workflow, node)({'error_message': 'Synthetic technical failure'}))
