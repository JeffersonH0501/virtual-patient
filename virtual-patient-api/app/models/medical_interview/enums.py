import enum

class InterviewStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class SenderType(str, enum.Enum):
    USER = "user"
    PATIENT = "patient"  # Changed from CHATBOT to PATIENT to match database constraint

class NoteType(str, enum.Enum):
    OBSERVATION = "observation"
    FEEDBACK = "feedback"