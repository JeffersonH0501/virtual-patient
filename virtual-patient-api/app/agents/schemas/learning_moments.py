"""Independent pedagogical feedback; historical critical turns remain readable."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["show_interest", "show_empathy", "speak_clearly"]
Evidence = Literal["text", "gaze_orientation", "head_nods", "smile_activity", "speech_timing", "prosodic_level", "prosodic_variability"]


class LearningMoment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    type: Literal["strength", "improvement"]
    turn_ids: list[str] = Field(min_length=1)
    observation: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    evidence_used: list[Evidence] = Field(min_length=1)

    @field_validator("turn_ids", "evidence_used")
    @classmethod
    def unique_references(cls, values):
        if any(not value.strip() for value in values) or len(values) != len(set(values)):
            raise ValueError("References must be nonempty and unique")
        return values


class LearningMomentsOutput(BaseModel):
    # Ignore provider envelope annotations; moment fields and limits stay strict.
    model_config = ConfigDict(extra="ignore")
    moments: list[LearningMoment] = Field(max_length=3)


class LearningMomentReferenceError(ValueError):
    pass


def validate_references(output, context):
    """Reject unknown turns and unsupported category/speaker/quality evidence."""
    for moment in output.moments:
        if moment.type != "improvement" or not (set(moment.evidence_used) - {"text"}):
            raise LearningMomentReferenceError("Learning moments must describe an improvement supported by multimodal evidence")
        if not set(moment.turn_ids).issubset(context["turn_ids"]):
            raise LearningMomentReferenceError("Learning moment references unavailable interview turns")
        available = {"text"}
        for turn_id in moment.turn_ids:
            available.update(context["evidence"][moment.category].get(turn_id, {}))
        if not set(moment.evidence_used).issubset(available):
            raise LearningMomentReferenceError("Learning moment references unauthorized or unavailable evidence")
        if any(not (set(moment.evidence_used) - {"text"}) & set(context["evidence"][moment.category].get(turn_id, {})) for turn_id in moment.turn_ids):
            raise LearningMomentReferenceError("Each referenced turn must contain the cited multimodal evidence")
    return output
