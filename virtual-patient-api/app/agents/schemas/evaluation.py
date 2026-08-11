from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

class EvaluationResult(BaseModel):
    """Schema for evaluation results"""
    aspect: str = Field(..., description="The aspect being evaluated (e.g., clarity, empathy, friendliness)")
    score: float = Field(..., ge=1.0, le=10.0, description="Score from 1 to 10 (allows decimal values like 4.5)")
    feedback: str = Field(..., description="Detailed feedback explaining the score and recommendations")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
