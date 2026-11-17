"""Provider lineage retains exact prompt messages and recognized metadata."""
import hashlib

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from app.agents.evaluation_provenance import EvaluationProvenanceCallback


def test_callback_keeps_only_provider_metadata():
    records = []
    response = LLMResult(generations=[[ChatGeneration(message=AIMessage(
        content="Private conversation content", response_metadata={
            "model_name": "test-model", "system_fingerprint": "test-fingerprint",
            "token_usage": {"total_tokens": 20}, "private_field": "Private data",
        },
    ))]])
    system_prompt = "Synthetic evaluation prompt"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content="Private conversation content")]
    EvaluationProvenanceCallback(records, "show_interest", system_prompt, messages).on_llm_end(response)
    assert records == [{"aspect": "show_interest", "model_name": "test-model",
                        "prompt_messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "human", "content": "Private conversation content"},
                        ],
                        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
                        "system_fingerprint": "test-fingerprint", "token_usage": {"total_tokens": 20}}]
