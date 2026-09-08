from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

EVALUATION_SCORE_MIN = 0.0
EVALUATION_SCORE_MAX = 5.0

class EvaluationResult(BaseModel):
    """Schema for evaluation results"""
    aspect: str = Field(..., description="The aspect being evaluated (e.g., clarity, empathy, friendliness)")
    score: float = Field(
        ...,
        ge=EVALUATION_SCORE_MIN,
        le=EVALUATION_SCORE_MAX,
        description="Score from 0 to 5 (allows decimal values like 3.5)",
    )
    feedback: str = Field(..., description="Detailed feedback explaining the score and recommendations")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
