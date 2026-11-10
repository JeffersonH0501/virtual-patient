"""Record provider metadata without logging conversation or prompt contents."""
import hashlib

from langchain_core.callbacks import BaseCallbackHandler


class EvaluationProvenanceCallback(BaseCallbackHandler):
    def __init__(self, records, aspect, system_prompt):
        self.records = records
        self.aspect = aspect
        self.system_prompt_sha256 = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()

    def on_llm_end(self, response, **kwargs):
        metadata = dict(response.llm_output or {})
        for group in response.generations:
            for generation in group:
                message = getattr(generation, "message", None)
                metadata.update(getattr(message, "response_metadata", {}) or {})
        self.records.append({"aspect": self.aspect, "system_prompt_sha256": self.system_prompt_sha256,
                             **{key: metadata[key] for key in (
            "model_name", "model", "system_fingerprint", "token_usage", "finish_reason",
        ) if key in metadata}})
