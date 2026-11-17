"""Independent pedagogical feedback; historical critical turns remain readable.

A learning moment is a single, highly specific improvement for one multimodal
category, centered on HOW the student delivered one part of the interview.
Generation runs once per category and returns at most one moment.

The model's wording is stored as returned. The code only fixes what it already
knows (the category of the call and the evidence present on the cited turns) and
checks that the cited turns exist, because the interface links to them.
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["show_interest", "show_empathy", "speak_clearly"]
Evidence = Literal["text", "gaze_orientation", "head_nods", "smile_activity", "speech_timing", "prosodic_level", "prosodic_variability"]


class LearningMoment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    turn_ids: list[str] = Field(min_length=1, max_length=2)
    # One short connected paragraph: where it happened, what the voice or body did, the problem and the change.
    text: str = Field(min_length=1)
    evidence_used: list[Evidence] = Field(min_length=1)

    @field_validator("turn_ids", "evidence_used")
    @classmethod
    def unique_references(cls, values):
        if any(not value.strip() for value in values) or len(values) != len(set(values)):
            raise ValueError("References must be nonempty and unique")
        return values


class LearningMomentOutput(BaseModel):
    # Ignore provider envelope annotations; the single optional moment stays strict.
    model_config = ConfigDict(extra="ignore")
    moment: Optional[LearningMoment] = None


class LearningMomentReferenceError(ValueError):
    pass


def validate_moment(moment, category, context):
    """Keep a moment only if its cited turns exist in this interview (the UI links to them)."""
    if moment is None:
        return None
    if moment.category != category:
        raise LearningMomentReferenceError("Moment category must match the generated category")
    if not set(moment.turn_ids).issubset(context["turn_ids"]):
        raise LearningMomentReferenceError("Learning moment references unavailable interview turns")
    return moment
