"""Record provider metadata and the exact messages sent for each evaluation call."""
import hashlib

from langchain_core.callbacks import BaseCallbackHandler


class EvaluationProvenanceCallback(BaseCallbackHandler):
    def __init__(self, records, aspect, system_prompt, prompt_messages=None):
        self.records = records
        self.aspect = aspect
        self.system_prompt_sha256 = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        self.prompt_messages = [
            {"role": getattr(message, "type", "unknown"), "content": message.content}
            for message in (prompt_messages or [])
        ]

    def on_llm_end(self, response, **kwargs):
        metadata = dict(response.llm_output or {})
        for group in response.generations:
            for generation in group:
                message = getattr(generation, "message", None)
                metadata.update(getattr(message, "response_metadata", {}) or {})
        self.records.append({"aspect": self.aspect, "system_prompt_sha256": self.system_prompt_sha256,
                             **({"prompt_messages": self.prompt_messages} if self.prompt_messages else {}),
                             **{key: metadata[key] for key in (
            "model_name", "model", "system_fingerprint", "token_usage", "finish_reason",
        ) if key in metadata}})
