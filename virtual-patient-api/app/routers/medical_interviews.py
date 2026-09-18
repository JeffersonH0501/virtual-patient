import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Literal, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field, model_validator
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.multimodal.schemas import PersonalBaseline
from app.models.user import User, UserRole
from app.models.medical_interview import (
    MedicalInterviewDB, MedicalInterview, MedicalInterviewCreate, MedicalInterviewUpdate,
    MedicalInterviewComplete, MedicalInterviewWithScore
)
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.progress_summary_controller import ProgressSummaryController
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.controllers.personality_controller import PersonalityController
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.schemas import EvaluationResult
from app.utils.language import (
    convert_language_code_to_name,
    resolve_ui_language,
    with_patient_response_language,
)
from app.media.storage import get_media_storage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/medical-interviews", 
    tags=["medical-interviews"],
    responses={404: {"description": "Interview not found"}},
)


class InterviewResponse(BaseModel):
    interview: MedicalInterview | None

class CompleteInterviewResponse(BaseModel):
    interview: MedicalInterview
    evaluation_results: List[EvaluationResult]


class CompleteInterviewRequest(BaseModel):
    completion_reason: Literal["user_completed"] = "user_completed"


# Non-terminal observation_processing statuses reported by the multimodal
# pipeline (see app/multimodal/pipeline.py STATUS_*). While a run is in one of
# these states its per-turn result is not yet available.
_PENDING_OBSERVATION_STATUSES = frozenset({"queued", "processing"})

# Whether the multimodal pipeline result is a REQUIRED input to interview
# completion. In this feature it is not: Bayona's textual evaluation remains the
# baseline and the only required input to the final feedback, and no late fusion
# is implemented (Requirements 17.4, 20.4). Flip this to ``True`` once late
# fusion makes the multimodal result required for completion.
_MULTIMODAL_REQUIRED_FOR_COMPLETION = False


def _required_multimodal_processing_pending(
    interview: MedicalInterviewDB,
) -> bool:
    """Report whether REQUIRED multimodal processing is still in flight.

    Requirement 20.3 forbids leaving an interview ``COMPLETED`` while required
    multimodal processing is pending. In this feature the multimodal pipeline is
    a best-effort, non-blocking hand-off scheduled at recording finalize; its
    lifecycle stays independently observable in
    ``recording.capture_config["observation_processing"]`` (written by the
    pipeline) and is never conflated with the interview status (Requirement
    20.2). Because the multimodal result is not yet required, a pending or
    partial run must not block or corrupt the interview lifecycle.

    This helper centralizes the decision so completion can be gated in one place
    once late fusion makes the multimodal result required. Today, with
    ``_MULTIMODAL_REQUIRED_FOR_COMPLETION`` false, it always reports ``False``.
    """
    if not _MULTIMODAL_REQUIRED_FOR_COMPLETION:
        return False
    recording = interview.recording
    if recording is None:
        return False
    observation = (recording.capture_config or {}).get("observation_processing", {})
    return observation.get("status") in _PENDING_OBSERVATION_STATUSES


class CalibrationResultRequest(BaseModel):
    """A calibration draft persisted into an interview before it starts.

    This mirrors the temporary-processing result the client keeps in memory
    (``POST /calibration/process``). Only a ``passed`` calibration carries the
    numeric ``personal_baseline`` and the ``profile`` needed by the multimodal
    pipeline (including the gaze affine matrix). The ``personal_baseline`` is
    validated against the strong :class:`PersonalBaseline` schema: an ill-formed
    payload is rejected, and a passed calibration must carry both a baseline and
    a profile so the interview always has a usable calibration once started.
    """

    version: str = "multimodal_calibration_v1"
    status: Literal["passed", "failed"]
    failure_reason: str | None = None
    profile: Dict[str, Any] | None = None
    quality: Dict[str, Any] | None = None
    personal_baseline: PersonalBaseline | None = None

    @model_validator(mode="after")
    def validate_passed_result(self):
        if self.status == "passed" and (self.personal_baseline is None or self.profile is None):
            raise ValueError("A passed calibration must carry a personal baseline and profile")
        return self

def translate_interview_personality(interview_dict: Dict[str, Any], user_language: str) -> None:
    """Helper to translate personality name in interview dict"""
    if interview_dict.get('personality'):
        PersonalityController.translate_personality_name_in_dict(
            interview_dict['personality'], 
            user_language
        )


def localize_interview_content(
    interview_dict: Dict[str, Any],
    language: str,
) -> None:
    """Localize visible interview metadata without changing patient speech language."""
    translate_interview_personality(interview_dict, language)
    clinical_case = interview_dict.get("clinical_case")
    if not clinical_case or language == "en":
        return

    for field_name in ("title", "description"):
        translations = clinical_case.get(f"{field_name}_translations") or {}
        translated_value = translations.get(language)
        if translated_value:
            clinical_case[field_name] = translated_value

@router.post("", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    interview_data: MedicalInterviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new medical interview session.
    
    - **clinical_case_id**: ID of the clinical case for this interview (required)
    - **interview_metadata**: Additional interview metadata (optional)
    - **patient_name**: Name of the patient for this interview (optional)
    - **patient_photo**: Photo URL/path of the patient (optional)
    - **patient_gender**: Gender of the patient (optional) - if provided and patient_name is not provided, will auto-select name from clinical case
    - **personality_id**: ID of the personality for the virtual patient (optional)

    Returns the created interview with session details.
    
    Note: If patient_gender is provided but patient_name is not, the system will automatically
    select the appropriate name (female_name or male_name) and photo from the clinical case.
    """
    if current_user.role == UserRole.SUPERUSER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superusers cannot start medical interview simulations",
        )

    service = MedicalInterviewController(db)

    # A student may only run one interview at a time: block creation while an
    # already started (in-progress) interview exists.
    active_interview = service.get_active_started_interview(current_user.id)
    if active_interview is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an interview in progress",
        )

    interview_metadata = with_patient_response_language(
        interview_data.interview_metadata,
        interview_data.patient_response_language,
    )
    interview_metadata.pop("calibration", None)
    
    interview = service.create_interview(
        user_id=current_user.id,
        clinical_case_id=interview_data.clinical_case_id,
        interview_metadata=interview_metadata,
        patient_name=interview_data.patient_name,
        patient_photo=interview_data.patient_photo,
        patient_gender=interview_data.patient_gender,
        personality_id=interview_data.personality_id
    )
    
    return InterviewResponse(interview=interview)


@router.put("/{interview_id}/calibration", response_model=MedicalInterview)
async def save_calibration_result(
    interview_id: int,
    calibration: CalibrationResultRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Persist a calibration draft into an interview before it starts.

    The draft is produced by the temporary ``POST /calibration/process`` flow and
    kept in the client's memory. This endpoint stores the whole calibration
    result (status, profile, quality, personal baseline) into
    ``interview_metadata.calibration`` so the multimodal pipeline can read the
    gaze affine profile and personal baseline from a single canonical location
    (``read_personal_baseline``). No calibration media is retained and no
    calibration table row is created.

    Calibration can only be saved before the interview starts: the request is
    rejected with 409 once ``start_time`` is set, preventing an arbitrary
    overwrite of the calibration an in-progress session already relies on.
    """
    interview = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id,
        MedicalInterviewDB.user_id == current_user.id,
    ).first()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if interview.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview is not in progress")
    if interview.start_time is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The interview has already started")

    # ``personal_baseline`` is serialized as a plain dict so
    # ``read_personal_baseline`` reads it back through the ``PersonalBaseline``
    # schema. The profile (including the gaze affine matrix) is preserved for the
    # multimodal pipeline.
    result = calibration.model_dump()
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    metadata = dict(interview.interview_metadata or {})
    metadata["calibration"] = result
    interview.interview_metadata = metadata
    flag_modified(interview, "interview_metadata")
    db.commit()
    db.refresh(interview)
    return MedicalInterview.from_orm(interview)


@router.post("/{interview_id}/start", response_model=MedicalInterview)
async def start_interview(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Start the official interview clock after successful calibration."""
    service = MedicalInterviewController(db)
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this interview")
    interview = service.start_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview

@router.get("/{interview_id}", response_model=MedicalInterviewComplete)
async def get_interview(
    interview_id: int,
    language: Optional[Literal["en", "es"]] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get interview details by ID.
    
    - **interview_id**: Unique identifier for the interview
    
    Returns complete interview information including evaluation if completed.
    """
    service = MedicalInterviewController(db)
    
    # Validate access
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    interview = service.get_interview_complete(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Check if interview is completed and has evaluation
    if interview.status == "completed":
        evaluation_controller = InterviewEvaluationController(db)
        evaluation = evaluation_controller.get_evaluation_by_interview_id(interview_id)
        if evaluation:
            # Add evaluation to the interview object
            interview.interview_evaluation = evaluation
    
    # Add isOwner field to the response
    interview_dict = interview.model_dump() if hasattr(interview, 'model_dump') else interview.dict()
    interview_dict['isOwner'] = interview_dict.get('user_id') == current_user.id
    
    interface_language = resolve_ui_language(language, current_user.preferred_language)
    localize_interview_content(interview_dict, interface_language)
    
    return interview_dict

@router.get("/{interview_id}/complete", response_model=MedicalInterviewComplete)
async def get_interview_complete(
    interview_id: str,
    language: Optional[Literal["en", "es"]] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get interview with all related data (messages, hypotheses, summary, etc.).
    
    - **interview_id**: Unique identifier for the interview
    
    Returns complete interview information including all related entities.
    """
    service = MedicalInterviewController(db)
    
    # Validate access
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    interview = service.get_interview_complete(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Add isOwner field to the response
    interview_dict = interview.model_dump() if hasattr(interview, 'model_dump') else interview.dict()
    interview_dict['isOwner'] = interview_dict.get('user_id') == current_user.id
    
    interface_language = resolve_ui_language(language, current_user.preferred_language)
    localize_interview_content(interview_dict, interface_language)
    
    return interview_dict

@router.get("", response_model=List[MedicalInterviewWithScore])
async def get_user_interviews(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all interviews for the current user with evaluation scores.
    
    - **skip**: Number of interviews to skip (for pagination)
    - **limit**: Maximum number of interviews to return
    
    Returns a list of user's interviews with evaluation scores (null if no evaluation exists).
    """
    interview_controller = MedicalInterviewController(db)
    interviews_with_scores = interview_controller.get_user_interviews_with_scores(
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )
    
    # Translate personality names based on user's preferred language
    user_language = current_user.preferred_language or "en"
    for interview in interviews_with_scores:
        interview_dict = interview if isinstance(interview, dict) else (interview.model_dump() if hasattr(interview, 'model_dump') else interview.dict())
        translate_interview_personality(interview_dict, user_language)
    
    return interviews_with_scores

@router.get("/organization/{organization_id}", response_model=List[Dict[str, Any]])
async def get_interviews_by_organization(
    organization_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all student medical interviews (ignoring organization_id parameter).

    - **organization_id**: Unique identifier for the organization (ignored in logic)
    - **skip**: Number of interviews to skip (for pagination)
    - **limit**: Maximum number of interviews to return

    Returns a list of student interviews with evaluation scores and additional context including:
    - organization_id: The organization ID (for compatibility)
    - clinical_case_title: Title of the clinical case
    - user_name: Name of the student who conducted the interview
    - evaluation_score: Overall evaluation score (null if no evaluation exists)
    - teacher_feedback: List of teacher feedback for the interview
    """
    interview_controller = MedicalInterviewController(db)
    interviews = interview_controller.get_interviews_by_organization(
        organization_id=organization_id,
        current_user=current_user,
        skip=skip,
        limit=limit
    )
    
    # Translate personality names based on user's preferred language
    user_language = current_user.preferred_language or "en"
    for interview in interviews:
        translate_interview_personality(interview, user_language)
    
    return interviews

@router.post("/{interview_id}", response_model=MedicalInterview)
async def update_interview(
    interview_id: str,
    update_data: MedicalInterviewUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update interview status and metadata.
    
    - **interview_id**: Unique identifier for the interview
    - **update_data**: Fields to update (status, session_ended_at, metadata)
    
    Returns the updated interview.
    """
    service = MedicalInterviewController(db)
    if update_data.interview_metadata and "calibration" in update_data.interview_metadata:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use the calibration endpoint to update technical calibration",
        )
    
    # Validate access
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    interview = service.update_interview(interview_id, update_data)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    return interview

@router.post("/{interview_id}/complete", response_model=CompleteInterviewResponse)
async def complete_interview(
    interview_id: str,
    completion_data: CompleteInterviewRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Complete an interview session and get evaluation results.
    
    - **interview_id**: Unique identifier for the interview
    
    Marks the interview as completed, sets the end time, and returns evaluation results.
    """
    interview_controller = MedicalInterviewController(db)
    
    # Validate access
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )

    interview_to_complete = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id
    ).first()
    if not interview_to_complete or interview_to_complete.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview has not started",
        )

    # An interview without a durable recording cannot be evaluated. Its
    # conversation transcript is still preserved, but the interview is marked as
    # interrupted and receives no evaluation.
    if interview_to_complete.recording is None:
        interrupted = interview_controller.interrupt_processing(interview_id)
        if interrupted is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found",
            )
        return CompleteInterviewResponse(
            interview=interrupted,
            evaluation_results=[],
        )

    print(f"Interview ID: {interview_id}")    
    
    try:
        completion_reason = (
            completion_data.completion_reason
            if completion_data is not None
            else "user_completed"
        )
        interview_record = db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id
        ).first()
        if interview_record:
            metadata = dict(interview_record.interview_metadata or {})
            metadata["completion_reason"] = completion_reason
            interview_record.interview_metadata = metadata
            db.commit()

        # The interaction with the virtual patient has ended: mark the interview
        # as processing while the evaluation and feedback are generated. The
        # evaluation runs synchronously below, so this window is short, but the
        # state is still recorded so the lifecycle is observable and consistent.
        if interview_controller.mark_processing(interview_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        print(f"Evaluate interview")

        # Get evaluation data
        evaluation_data = interview_controller.get_interview_evaluation_data(interview_id)
        # Format messages for evaluation
        formatted_messages = interview_controller.format_messages_for_evaluation(
            evaluation_data["messages"]
        )
        
        # Initialize evaluation agent with user's preferred language and patient gender
        user_language_code = current_user.preferred_language or "en"
        user_language_name = convert_language_code_to_name(user_language_code)
        patient_gender = interview_to_complete.patient_gender
        evaluation_agent = EvaluationAgent(target_language=user_language_name, patient_gender=patient_gender)
        
        # Run all evaluations in parallel (includes completeness + conversation aspects)
        evaluation_results = []
        try:
            # Get hypotheses from evaluation data
            hypotheses = evaluation_data.get("hypotheses", [])
            
            evaluation_results = await evaluation_agent.evaluate_all_aspects(
                conversation_messages=formatted_messages,
                clinical_case=evaluation_data["clinical_case"],
                progress_summary=evaluation_data["progress_summary"],
                hypotheses=hypotheses,
                aspects=["general_communication", "completeness", "show_interest", "show_empathy", "speak_clearly", "open_communication"]
            )
        except Exception as e:
            print(f"Error in evaluations: {e}")
        
        # Store evaluation results in database
        if evaluation_results:
            try:
                evaluation_controller = InterviewEvaluationController(db)
                
                # Calculate overall score
                overall_score = evaluation_controller.calculate_overall_score(evaluation_results)
                
                # Create evaluation data
                from app.models.medical_interview import InterviewEvaluationCreate
                evaluation_data = InterviewEvaluationCreate(
                    evaluation_results=evaluation_results,
                    overall_score=overall_score
                )
                
                # Store evaluation
                stored_evaluation = evaluation_controller.create_evaluation(interview_id, evaluation_data)
                print(f"Stored evaluation with ID: {stored_evaluation.id}")
                
            except Exception as e:
                print(f"Error storing evaluation: {e}")
                # Continue even if storage fails

        # Coordinate the interview lifecycle with multimodal processing
        # (Requirement 20.3). The multimodal pipeline runs as a best-effort
        # background task scheduled at recording finalize and is not yet a
        # required input to the final feedback (text evaluation is the baseline;
        # no late fusion in this feature). If a required multimodal step were
        # pending, we would keep the interview in PROCESSING rather than
        # COMPLETED; today no such step gates completion, so we complete after
        # the (required) text evaluation. The multimodal observation lifecycle
        # remains independently observable via the recording and is never turned
        # into a second interview lifecycle (Requirement 20.2).
        if _required_multimodal_processing_pending(interview_to_complete):
            logger.info(
                "complete_interview interview_id=%s event=deferred_completion "
                "reason=required_multimodal_processing_pending",
                interview_id,
            )
            return CompleteInterviewResponse(
                interview=MedicalInterview.from_orm(interview_to_complete),
                evaluation_results=evaluation_results,
            )

        # Processing finished: mark the interview as completed and set its end
        # time. The evaluation and feedback are now available to the student.
        interview = interview_controller.complete_interview(interview_id)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )

        return CompleteInterviewResponse(
            interview=interview,
            evaluation_results=evaluation_results
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "complete_interview interview_id=%s event=failed", interview_id
        )
        # Processing failed after the interaction ended: leave the interview in a
        # terminal INTERRUPTED state instead of a stuck PROCESSING state.
        try:
            interview_controller.interrupt_processing(interview_id)
        except Exception:
            logger.exception(
                "complete_interview interview_id=%s event=interrupt_cleanup_failed",
                interview_id,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error completing interview: {str(e)}"
        )

@router.post("/{interview_id}/abandon", response_model=MedicalInterview)
async def abandon_interview(
    interview_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Abandon an interview session.
    
    - **interview_id**: Unique identifier for the interview
    
    Marks the interview as abandoned and sets the end time.
    """
    service = MedicalInterviewController(db)
    
    # Validate access
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    interview = service.abandon_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    from app.multimodal.turn_video_queue import fail_pending_turn_video_jobs
    fail_pending_turn_video_jobs(db, int(interview_id), "interview_interrupted")
    
    return interview

@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently delete an owned interview and its private media."""
    interview = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id,
        MedicalInterviewDB.user_id == current_user.id,
    ).first()
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    numeric_interview_id = interview.id
    try:
        # This summary references the last message independently of its interview
        # relationship, so it must be removed before cascading message deletion.
        if interview.progress_summary is not None:
            interview.progress_summary = None
            db.flush()
        db.delete(interview)
        db.flush()
        get_media_storage().delete_interview(numeric_interview_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to permanently delete interview",
            extra={"interview_id": numeric_interview_id, "user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interview deletion failed",
        )

    logger.info(
        "Interview permanently deleted",
        extra={"interview_id": numeric_interview_id, "user_id": current_user.id},
    )
    return None


@router.get("/organization/{organization_id}/active-students-count")
async def get_active_students_count_by_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the count of students who have active conversations (ignoring organization_id parameter).

    - **organization_id**: Unique identifier for the organization (ignored in logic)

    Returns the count of distinct students with active interviews.
    """
    interview_controller = MedicalInterviewController(db)
    count = interview_controller.count_active_student_conversations_by_organization(
        organization_id=organization_id
    )
    return {"organization_id": organization_id, "active_students_count": count}


@router.get("/organization/{organization_id}/completed-students-count")
async def get_completed_students_count_by_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the count of students who have completed conversations (ignoring organization_id parameter).

    - **organization_id**: Unique identifier for the organization (ignored in logic)

    Returns the count of distinct students with completed interviews.
    """
    interview_controller = MedicalInterviewController(db)
    count = interview_controller.count_completed_student_conversations_by_organization(
        organization_id=organization_id
    )
    return {"organization_id": organization_id, "completed_students_count": count}


@router.get("/organization/{organization_id}/average-score")
async def get_average_score_by_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the average evaluation score for all conversations (ignoring organization_id parameter).

    - **organization_id**: Unique identifier for the organization (ignored in logic)

    Returns the average score, total evaluations count, and whether data exists.
    """
    interview_controller = MedicalInterviewController(db)
    result = interview_controller.get_average_score_by_organization(
        organization_id=organization_id
    )
    return result


@router.get("/my/active", response_model=Optional[MedicalInterview])
async def get_my_active_interview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the current user's in-progress interview, if any.

    An interview is in progress once it has started (start_time is set after
    calibration) and has not been completed or interrupted. A student may only
    have one such interview at a time. Returns null when there is none, so the
    client can offer to resume it or force its termination on re-entry.
    """
    interview_controller = MedicalInterviewController(db)
    active = interview_controller.get_active_started_interview(current_user.id)
    if active is None:
        return None
    return MedicalInterview.from_orm(active)


@router.get("/my/completed-cases")
async def get_my_completed_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the count of completed cases for the current user.
    
    Returns the count of completed interviews for the authenticated user.
    """
    interview_controller = MedicalInterviewController(db)
    count = interview_controller.count_completed_cases_for_user(current_user.id)
    return {"user_id": current_user.id, "completed_cases_count": count}


@router.get("/my/average-duration")
async def get_my_average_duration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the average duration of completed cases for the current user.
    
    Returns the average duration in seconds for completed interviews of the authenticated user.
    """
    interview_controller = MedicalInterviewController(db)
    result = interview_controller.get_average_duration_for_user(current_user.id)
    return result


@router.get("/my/average-score")
async def get_my_average_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the average evaluation score for the current user's conversations.
    
    Returns the average score, total evaluations count, and whether data exists for the authenticated user.
    """
    interview_controller = MedicalInterviewController(db)
    result = interview_controller.get_average_score_for_user(current_user.id)
    return result
