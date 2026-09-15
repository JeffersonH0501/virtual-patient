import enum

class InterviewStatus(str, enum.Enum):
    """Lifecycle states of a medical interview.

    IN_PROGRESS: the student started the simulation and has not finished the
        interaction with the virtual patient yet.
    PROCESSING: the interaction ended and the system is processing the collected
        information to generate the evaluation and feedback.
    COMPLETED: the interview and its processing finished successfully; the
        evaluation and feedback are available to the student.
    INTERRUPTED: the interview did not complete its flow successfully, whether
        because the student abandoned it, the session was interrupted, or an
        error occurred during processing.
    """

    IN_PROGRESS = "in_progress"
    PROCESSING = "processing"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"

class SenderType(str, enum.Enum):
    USER = "user"
    PATIENT = "patient"  # Changed from CHATBOT to PATIENT to match database constraint

class NoteType(str, enum.Enum):
    OBSERVATION = "observation"
    FEEDBACK = "feedback"