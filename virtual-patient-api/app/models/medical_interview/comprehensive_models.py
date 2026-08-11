from __future__ import annotations
from typing import List, Optional
from .medical_interview import MedicalInterview
from .interview_message import InterviewMessage
from .user_hypothesis import UserHypothesis
from .medical_session_note import MedicalSessionNote
from .progress_summary import ProgressSummary
from .interview_evaluation import InterviewEvaluation
from app.models.clinical_case import ClinicalCase

# Comprehensive models with relationships
class MedicalInterviewWithMessages(MedicalInterview):
    messages: List[InterviewMessage] = []

class MedicalInterviewWithHypotheses(MedicalInterview):
    hypotheses: List[UserHypothesis] = []

class MedicalInterviewWithNotes(MedicalInterview):
    session_notes: List[MedicalSessionNote] = []

class MedicalInterviewWithSummary(MedicalInterview):
    progress_summary: Optional[ProgressSummary] = None

class MedicalInterviewComplete(MedicalInterview):
    messages: List[InterviewMessage] = []
    hypotheses: List[UserHypothesis] = []
    session_notes: List[MedicalSessionNote] = []
    progress_summary: Optional[ProgressSummary] = None
    interview_evaluation: Optional[InterviewEvaluation] = None
    clinical_case: Optional[ClinicalCase] = None
    isOwner: Optional[bool] = None 