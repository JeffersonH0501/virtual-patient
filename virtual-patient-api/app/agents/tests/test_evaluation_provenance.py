"""Provider lineage excludes message bodies and unrecognized metadata."""
import hashlib

from langchain_core.messages import AIMessage
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
    EvaluationProvenanceCallback(records, "show_interest", system_prompt).on_llm_end(response)
    assert records == [{"aspect": "show_interest", "model_name": "test-model",
                        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
                        "system_fingerprint": "test-fingerprint", "token_usage": {"total_tokens": 20}}]
