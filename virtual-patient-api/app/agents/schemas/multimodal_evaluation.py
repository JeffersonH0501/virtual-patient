"""Separate structured output; the legacy evaluator schema is unchanged."""

from pydantic import BaseModel, Field, field_validator
from .evaluation import EvaluationResult


class CriticalTurn(BaseModel):
    turn_id: str = Field(description="Persistent InterviewTurnDB UUID included in the conversation")
    annotation: str = Field(min_length=1, description="Observed issue and its contextual effect on the criterion")


class MultimodalEvaluationResult(EvaluationResult):
    critical_turns: list[CriticalTurn] = Field(default_factory=list, max_length=3)

    @field_validator("critical_turns", mode="before")
    @classmethod
    def limit_turns(cls, value):
        # Reference filtering happens before validation in the agent. Also bound
        # standalone API/model construction without changing the legacy schema.
        return value[:3] if isinstance(value, list) else value


def validate_multimodal_result(payload: dict, aspect: str, turn_ids: frozenset[str]):
    """Filter references before truncation and structured output validation."""
    payload = dict(payload)
    seen = set()
    valid = []
    for turn in payload.get("critical_turns", []):
        if not isinstance(turn, dict):
            continue
        identifier = turn.get("turn_id")
        annotation = turn.get("annotation")
        if isinstance(identifier, str) and identifier in turn_ids and identifier not in seen and isinstance(annotation, str) and annotation.strip():
            seen.add(identifier)
            valid.append({"turn_id": identifier, "annotation": annotation.strip()})
    payload["aspect"] = aspect
    payload["critical_turns"] = valid[:3]
    return MultimodalEvaluationResult.model_validate(payload)
