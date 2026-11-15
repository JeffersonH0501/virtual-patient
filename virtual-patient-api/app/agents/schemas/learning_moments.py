"""Independent pedagogical feedback; historical critical turns remain readable.

A learning moment is a single, highly specific improvement or strength for one
multimodal category. It must be grounded in paraverbal or nonverbal evidence: a
purely textual observation no longer produces a moment. Generation runs once per
category per type (improvement, strength) and returns at most one moment each, so
the per-call output carries an optional moment.
"""
from typing import Literal, Optional
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal["show_interest", "show_empathy", "speak_clearly"]
Evidence = Literal["text", "gaze_orientation", "head_nods", "smile_activity", "speech_timing", "prosodic_level", "prosodic_variability"]
MomentType = Literal["improvement", "strength"]


class LearningMoment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    turn_ids: list[str] = Field(min_length=1, max_length=2)
    observation: str = Field(min_length=1)
    recommendation: str = Field(min_length=1, default="")
    reinforcement: str = Field(min_length=1, default="")
    evidence_used: list[Evidence] = Field(min_length=1)
    moment_type: MomentType = "improvement"

    @field_validator("turn_ids", "evidence_used")
    @classmethod
    def unique_references(cls, values):
        if any(not value.strip() for value in values) or len(values) != len(set(values)):
            raise ValueError("References must be nonempty and unique")
        return values

    @model_validator(mode="after")
    def validate_moment_type_fields(self):
        if self.moment_type == "improvement" and not self.recommendation:
            raise ValueError("Improvement moments must have a recommendation")
        if self.moment_type == "strength" and not self.reinforcement:
            raise ValueError("Strength moments must have a reinforcement")
        if self.moment_type == "improvement" and self.reinforcement:
            raise ValueError("Improvement moments should not have reinforcement")
        if self.moment_type == "strength" and self.recommendation:
            raise ValueError("Strength moments should not have recommendation")
        return self


class LearningMomentOutput(BaseModel):
    # Ignore provider envelope annotations; the single optional moment stays strict.
    model_config = ConfigDict(extra="ignore")
    moment: Optional[LearningMoment] = None


class LearningMomentReferenceError(ValueError):
    pass


def validate_moment(moment, category, context):
    """Reject unknown turns, foreign-category evidence and feedback that leaks IDs.

    A moment must be grounded in paraverbal or nonverbal evidence: at least one
    cited multimodal key is required, and every cited multimodal key must exist on
    the turns it is attributed to. A purely textual moment is rejected.
    """
    if moment is None:
        return None
    if moment.category != category:
        raise LearningMomentReferenceError("Moment category must match the generated category")
    if len(moment.turn_ids) > 2:
        raise LearningMomentReferenceError("Select at most two relevant turns per moment")
    if len(moment.turn_ids) == 2:
        numbers = [re.fullmatch(r"T(\d+)", turn_id) for turn_id in moment.turn_ids]
        if not all(numbers) or abs(int(numbers[0].group(1)) - int(numbers[1].group(1))) != 1:
            raise LearningMomentReferenceError("Two cited turns must be consecutive")
    if re.search(r"\b(?:T\s*\d+|turn(?:o|s|os)?\s*(?:#|n[úu]m(?:ero)?\.?\s*)?\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", f"{moment.observation} {moment.recommendation} {moment.reinforcement}", re.IGNORECASE):
        raise LearningMomentReferenceError("Do not mention turn identifiers or numbers in feedback text")
    if re.search(r"\d+(?:[.,]\d+)?\s*(?:%|ms\b|milisegundos|milliseconds|wpm|semitone|semitono|palabras por minuto|words per minute)|\b(?:F0|wpm)\b|semitono|semitone", f"{moment.observation} {moment.recommendation} {moment.reinforcement}", re.IGNORECASE):
        raise LearningMomentReferenceError("Do not quote measurements or technical units in feedback text")
    if not set(moment.turn_ids).issubset(context["turn_ids"]):
        raise LearningMomentReferenceError("Learning moment references unavailable interview turns")
    # The moment must be grounded in paraverbal/nonverbal evidence, not text alone.
    multimodal_used = set(moment.evidence_used) - {"text"}
    if not multimodal_used:
        raise LearningMomentReferenceError("Learning moment must cite paraverbal or nonverbal evidence, not text alone")
    # Each cited multimodal key must exist on every referenced turn.
    for turn_id in moment.turn_ids:
        available = set(context["evidence"][category].get(turn_id, {}))
        if not multimodal_used.issubset(available):
            raise LearningMomentReferenceError("Each referenced turn must contain the cited multimodal evidence")
    return moment
