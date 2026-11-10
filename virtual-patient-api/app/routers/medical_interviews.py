from app.core.review_access import can_replay, redact_interview
import asyncio
import logging
import json
from datetime import datetime, timezone
from time import perf_counter
from typing import List, Dict, Any, Literal, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field, model_validator
from app.core.database import SessionLocal, admit_review_transaction, get_db
from app.core.auth import get_current_active_user
from app.multimodal.schemas import PersonalBaseline
from app.models.user import User, UserDB, UserRole
from app.models.clinical_case import ClinicalCase
from app.models.medical_interview import (
    MedicalInterviewDB, MedicalInterview, MedicalInterviewCreate, MedicalInterviewUpdate,
    MedicalInterviewComplete, MedicalInterviewWithScore, InterviewRecordingDB,
    TurnVideoAnalysisDB, TurnVideoAnalysisStatus,
)
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.progress_summary_controller import ProgressSummaryController
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.controllers.personality_controller import PersonalityController
from app.controllers.interview_lifecycle import lock_row
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.schemas import EvaluationResult
from app.utils.language import (
    convert_language_code_to_name,
    resolve_ui_language,
    with_patient_response_language,
)
from app.media.storage import get_media_storage
from app.utils.runtime_metrics import current_rss_mb, process_id
from app.multimodal.evaluation_service import evaluate_and_store_multimodal, validate_text_control

logger = logging.getLogger(__name__)

_PENDING_TURN_ANALYSIS_STATUSES = frozenset({
    TurnVideoAnalysisStatus.QUEUED.value,
    TurnVideoAnalysisStatus.PROCESSING.value,
})
_TERMINAL_OBSERVATION_STATUSES = frozenset({
    "complete",
    "partial",
    "failed",
    "unavailable",
})
_ANALYSIS_COMPLETION_TIMEOUT_SECONDS = 1800.0
_ANALYSIS_COMPLETION_POLL_SECONDS = 0.5

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


async def _wait_for_multimodal_analysis(
    db: Session,
    interview_id: int,
    *,
    timeout_seconds: float = _ANALYSIS_COMPLETION_TIMEOUT_SECONDS,
) -> str:
    """Wait until the pipeline and every durable turn job are terminal.

    Returns the terminal ``observation_processing`` status. A timeout is an
    error: the interview must remain non-completed when analysis is unfinished.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        db.expire_all()
        recording = db.query(InterviewRecordingDB).filter(
            InterviewRecordingDB.medical_interview_id == interview_id,
        ).first()
        if recording is None:
            raise RuntimeError("Interview recording disappeared during analysis")

        observation = (recording.capture_config or {}).get(
            "observation_processing", {}
        )
        observation_status = observation.get("status")
        pending_turns = db.query(TurnVideoAnalysisDB.id).filter(
            TurnVideoAnalysisDB.medical_interview_id == interview_id,
            TurnVideoAnalysisDB.status.in_(_PENDING_TURN_ANALYSIS_STATUSES),
        ).count()
        if (
            observation_status in _TERMINAL_OBSERVATION_STATUSES
            and pending_turns == 0
        ):
            return observation_status

        if loop.time() >= deadline:
            raise TimeoutError(
                "Multimodal analysis did not finish before the completion timeout "
                f"(status={observation_status!r}, pending_turns={pending_turns})"
            )
        await asyncio.sleep(_ANALYSIS_COMPLETION_POLL_SECONDS)


async def _ensure_final_summary(db, interview_id, source_data, formatted_messages):
    """Summarize the frozen transcript using the existing canonical workflow."""
    from app.controllers.summary_controller import SummaryController
    from app.agents.schemas.progress_summary import ProgressSummarySchema
    controller = ProgressSummaryController(db)
    existing = controller.get_progress_summary_record(interview_id)
    last_id = source_data["messages"][-1].id if source_data["messages"] else None
    if existing is not None and existing.last_updated_message_id == last_id:
        return controller.get_progress_summary(interview_id)
    result = await SummaryController().process_summary(
        interview_id=interview_id,
        messages=[{"role": message["role"], "content": message["content"]} for message in formatted_messages],
        clinical_case=source_data["clinical_case"], user_preferred_language="English")
    summary = result.get("summary_result")
    if summary is None:
        raise RuntimeError("Final canonical summary generation returned no summary")
    if not isinstance(summary, ProgressSummarySchema):
        summary = ProgressSummarySchema.model_validate(summary)
    return controller.update_progress_summary(interview_id, summary, last_id,
        source_language="en", localized_versions={"en": summary.model_dump()})


async def _evaluate_and_complete_interview(
    interview_id: int,
    user_language_code: str,
    patient_gender: str | None,
) -> None:
    """Generate the textual evaluation after the completion request has returned."""
    overall_started = perf_counter()
    phase_started = overall_started
    timings_ms: Dict[str, float] = {}
    db = SessionLocal()
    interview_controller = MedicalInterviewController(db)
    try:
        source_data = interview_controller.get_interview_evaluation_data(interview_id)
        formatted_messages = interview_controller.format_messages_for_evaluation(
            source_data["messages"]
        )
        source_data["progress_summary"] = await _ensure_final_summary(db, interview_id, source_data, formatted_messages)
        timings_ms["data_load"] = (perf_counter() - phase_started) * 1000
        phase_started = perf_counter()
        evaluation_agent = EvaluationAgent(
            target_language=convert_language_code_to_name(user_language_code),
            patient_gender=patient_gender,
        )
        stored_control = InterviewEvaluationController(db).get_evaluation_by_interview_id(interview_id)
        evaluation_results = (stored_control.evaluation_results if stored_control is not None else await evaluation_agent.evaluate_all_aspects(
            conversation_messages=formatted_messages,
            clinical_case=source_data["clinical_case"],
            progress_summary=source_data["progress_summary"],
            hypotheses=source_data.get("hypotheses", []),
            aspects=[
                "general_communication",
                "completeness",
                "show_interest",
                "show_empathy",
                "speak_clearly",
                "open_communication",
            ],
        ))
        validate_text_control(evaluation_results)
        timings_ms["agent_evaluation"] = (perf_counter() - phase_started) * 1000
        phase_started = perf_counter()
        if evaluation_results:
            from app.models.medical_interview import InterviewEvaluationCreate

            evaluation_controller = InterviewEvaluationController(db)
            payload = InterviewEvaluationCreate(
                evaluation_results=evaluation_results,
                overall_score=evaluation_controller.calculate_overall_score(evaluation_results),
            )
            if evaluation_controller.get_evaluation_by_interview_id(interview_id) is None:
                from app.multimodal.evaluation_runs import stage_evaluation_run
                stage_evaluation_run(db, interview_id, payload.evaluation_condition, evaluation_agent, {
                    "canonical_messages": formatted_messages,
                    "clinical_case": source_data["clinical_case"],
                    "progress_summary": source_data["progress_summary"],
                    "hypotheses": source_data.get("hypotheses", []),
                    "prompts": evaluation_agent.evaluation_prompts,
                }, payload)
                evaluation_controller.create_evaluation(interview_id, payload)
        phase_started = perf_counter()
        logger.info(
            "performance_event component=interview_completion operation=wait_for_multimodal "
            "phase=started interview_id=%s",
            interview_id,
        )
        multimodal_status = await _wait_for_multimodal_analysis(db, interview_id)
        timings_ms["multimodal_wait"] = (perf_counter() - phase_started) * 1000
        if multimodal_status == "failed":
            raise RuntimeError("Multimodal analysis finished with a failed status")
        from app.models.medical_interview.interview_evaluation import EvaluationCondition
        stored_multimodal = InterviewEvaluationController(db).get_evaluation_by_interview_id(
            interview_id, EvaluationCondition.TEXT_PLUS_MULTIMODAL)
        if stored_multimodal is None:
            await evaluate_and_store_multimodal(
                db, interview_id, evaluation_agent, canonical_messages=formatted_messages,
            )
        else:
            validate_text_control(stored_multimodal.evaluation_results)
        phase_started = perf_counter()
        interview_controller.complete_interview(interview_id)
        timings_ms["persistence_and_completion"] = (perf_counter() - phase_started) * 1000
        logger.info(
            "performance_event component=interview_completion operation=text_evaluation phase=complete "
            "interview_id=%s duration_ms=%.3f aspect_count=%s timings_ms=%s "
            "worker_pid=%s worker_rss_mb=%s",
            interview_id, (perf_counter() - overall_started) * 1000,
            len(evaluation_results), json.dumps(timings_ms, sort_keys=True),
            process_id(), current_rss_mb(),
        )
    except Exception:
        logger.exception(
            "performance_event component=interview_completion operation=text_evaluation phase=failed "
            "interview_id=%s duration_ms=%.3f timings_ms=%s worker_pid=%s worker_rss_mb=%s",
            interview_id, (perf_counter() - overall_started) * 1000,
            json.dumps(timings_ms, sort_keys=True), process_id(), current_rss_mb(),
        )
        db.rollback()
        try:
            interview_controller.interrupt_processing(interview_id)
        except Exception:
            logger.exception(
                "complete_interview interview_id=%s event=interrupt_cleanup_failed",
                interview_id,
            )
    finally:
        db.close()


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
    attestations: Dict[str, str] = Field(default_factory=dict)
    resume_attempt_id: str | None = None

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
    if interview_data.calibration_test and current_user.role != UserRole.SUPERUSER:
        raise HTTPException(status_code=403, detail="Calibration tests are only available to superusers")
    if interview_data.calibration_test:
        raise HTTPException(status_code=410, detail="Use the temporary nonverbal test")
    if current_user.role == UserRole.SUPERUSER and not interview_data.calibration_test:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superusers cannot start medical interview simulations",
        )

    service = MedicalInterviewController(db)

    if interview_data.draft_request_id:
        lock_row(db, UserDB, current_user.id)
        existing_draft = db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.user_id == current_user.id,
            MedicalInterviewDB.interview_metadata["draft_request_id"].as_string() == interview_data.draft_request_id,
        ).first()
        if existing_draft is not None:
            return InterviewResponse(interview=MedicalInterview.from_orm(existing_draft))

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
    interview_metadata.pop("calibration_activity_at", None)
    interview_metadata.pop("calibration_discarded", None)
    interview_metadata.pop("calibration_test", None)
    interview_metadata.pop("draft_request_id", None)
    if interview_data.draft_request_id:
        interview_metadata["draft_request_id"] = interview_data.draft_request_id

    from app.models.clinical_case import ClinicalCaseDB, CaseType
    case = db.get(ClinicalCaseDB, interview_data.clinical_case_id)
    if case is None or case.case_type != CaseType.DEFAULT or not case.active:
        raise HTTPException(404, "Clinical case not found")
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

    The draft is produced by ``POST /calibration/process-stage`` and
    kept in the client's memory. This endpoint stores the whole calibration
    result (status, profile, quality, personal baseline) into
    ``interview_metadata.calibration`` so the multimodal pipeline can read the
    gaze affine profile and personal baseline from a single canonical location
    (``read_personal_baseline``). Signed capture IDs link this accepted profile
    to private calibration videos and outcomes retained separately.

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
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if not interview or interview.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if interview.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview is not in progress")
    attempt_id = calibration.resume_attempt_id
    if interview.start_time is not None and attempt_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The interview has already started")
    if attempt_id is not None:
        from app.media.calibration import require_pending_resume
        recording, attempt = require_pending_resume(db, interview, attempt_id)
        if calibration.status != "passed":
            raise HTTPException(422, "Resume requires a passed calibration")
    if (interview.interview_metadata or {}).get("calibration_discarded"):
        raise HTTPException(410, "Calibration preparation was discarded")

    # ``personal_baseline`` is serialized as a plain dict so
    # ``read_personal_baseline`` reads it back through the ``PersonalBaseline``
    # schema. The profile (including the gaze affine matrix) is preserved for the
    # multimodal pipeline.
    from app.multimodal.calibration_attestation import verify_calibration_checkpoints
    result = verify_calibration_checkpoints(current_user.id, interview_id, calibration.attestations, attempt_id) if calibration.status == "passed" else calibration.model_dump(exclude={"attestations", "resume_attempt_id"})
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    if attempt_id is not None:
        recording.capture_config = {**recording.capture_config, "resume_attempt": {**attempt, "calibration": result}}
        db.commit()
        return MedicalInterview.model_validate(interview)
    metadata = dict(interview.interview_metadata or {})
    metadata["calibration"] = result
    metadata["calibration_activity_at"] = datetime.now(timezone.utc).isoformat()
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
    if current_user.role == UserRole.SUPERUSER:
        raise HTTPException(status_code=403, detail="Superusers cannot start medical interview simulations")
    service = MedicalInterviewController(db)
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this interview")
    if not service.validate_interview_ownership(interview_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only the owner can start an interview")
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
    interview_dict = interview.model_dump()
    interview_dict['isOwner'] = interview_dict.get('user_id') == current_user.id
    
    interface_language = resolve_ui_language(language, current_user.preferred_language)
    localize_interview_content(interview_dict, interface_language)

    return redact_interview(db, db.get(MedicalInterviewDB, int(interview_id)), current_user, interview_dict)

@router.get("/{interview_id}/complete", response_model=MedicalInterviewComplete, dependencies=[Depends(admit_review_transaction)])
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
    interview_dict = interview.model_dump()
    interview_dict['isOwner'] = interview_dict.get('user_id') == current_user.id
    
    interface_language = resolve_ui_language(language, current_user.preferred_language)
    localize_interview_content(interview_dict, interface_language)
    
    if interview.status == "completed" and interview_dict.get("progress_summary"):
        from app.routers.summary import _resolve_localized_summary

        controller = ProgressSummaryController(db)
        stored_summary = controller.get_progress_summary(int(interview_id))
        if stored_summary is not None:
            try:
                localized = await _resolve_localized_summary(
                    int(interview_id), stored_summary, interface_language, controller,
                )
                interview_dict["progress_summary"].update(localized.model_dump())
            except Exception:
                db.rollback()
                logger.warning("Review summary localization failed interview_id=%s", interview_id)

    return redact_interview(db, db.get(MedicalInterviewDB, int(interview_id)), current_user, interview_dict)

@router.get("", response_model=List[MedicalInterviewWithScore])
def get_user_interviews(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
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
        limit=limit,
        include_assigned=current_user.role == UserRole.TEACHER,
    )
    
    # Translate personality names based on user's preferred language
    user_language = current_user.preferred_language or "en"
    for interview in interviews_with_scores:
        interview_dict = interview if isinstance(interview, dict) else (interview.model_dump())
        translate_interview_personality(interview_dict, user_language)
    
    return interviews_with_scores

def require_organization_staff(current_user: User, organization_id: int):
    """Keep organization history and metrics restricted to authorized staff."""
    if current_user.role != UserRole.SUPERUSER:
        raise HTTPException(status_code=403, detail="Organization staff access required")
    if current_user.organization_id is None or current_user.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")


@router.get("/organization/{organization_id}/interview-counts")
async def get_organization_interview_counts(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return interview totals in the same scope as organization history."""
    require_organization_staff(current_user, organization_id)
    return MedicalInterviewController(db).get_organization_interview_counts(organization_id, current_user)


@router.get("/organization/{organization_id}", response_model=List[Dict[str, Any]])
async def get_interviews_by_organization(
    organization_id: int,
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List started interviews in the caller's organization with an exact total."""
    require_organization_staff(current_user, organization_id)
    interview_controller = MedicalInterviewController(db)
    response.headers["X-Total-Count"] = str(
        interview_controller.count_organization_interviews(organization_id, current_user)
    )
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
    if update_data.interview_metadata and {"calibration_test", "missing_evidence_message_ids", "recording_transport", "calibration", "calibration_activity_at", "calibration_discarded", "completion_processing", "completion_reason", "draft_request_id", "message_request"}.intersection(update_data.interview_metadata):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use the dedicated endpoints to update server lifecycle metadata",
        )
    if not service.validate_interview_ownership(interview_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only the owner can update an interview")
    if update_data.status is not None or update_data.end_time is not None:
        raise HTTPException(status_code=422, detail="Use the dedicated interview lifecycle endpoints for status and timing")
    from app.controllers.interview_lifecycle import require_capture_open
    interview_record = lock_row(db, MedicalInterviewDB, int(interview_id))
    if interview_record is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    require_capture_open(interview_record)
    
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

@router.get("/{interview_id}/clinical-case", response_model=ClinicalCase)
def get_review_clinical_case(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Expose the source case to authorized reviewers after the conversation ends."""
    interview = db.get(MedicalInterviewDB, interview_id)
    if not can_replay(db, interview, current_user):
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.status not in {"processing", "completed"}:
        raise HTTPException(status_code=409, detail="The interview is not ready for review")
    case = ClinicalCaseController(db).get_clinical_case_in_language(
        interview.clinical_case_id, current_user.preferred_language or "en",
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Clinical case not found")
    return case


@router.post("/{interview_id}/complete", response_model=CompleteInterviewResponse)
def complete_interview(
    interview_id: str,
    completion_data: CompleteInterviewRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    storage = Depends(get_media_storage),
    capture_segment_id: str | None = Header(default=None, alias="X-Capture-Segment"),
):
    """
    Complete an interview session and get evaluation results.
    
    - **interview_id**: Unique identifier for the interview
    
    Marks the interview as completed, sets the end time, and returns evaluation results.
    """
    db.info['capture_wait'] = True
    interview_controller = MedicalInterviewController(db)
    
    # Validate access
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )

    interview_to_complete = lock_row(db, MedicalInterviewDB, int(interview_id))
    if interview_to_complete:
        from app.controllers.interview_lifecycle import require_no_pending_reply
        require_no_pending_reply(interview_to_complete)
    if interview_to_complete and interview_to_complete.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can complete an interview")
    if interview_to_complete:
        lifecycle_status = getattr(interview_to_complete.status, "value", interview_to_complete.status)
        if lifecycle_status in {"processing", "completed"}:
            return CompleteInterviewResponse(interview=interview_controller.get_interview(interview_id), evaluation_results=[])
        failure = (interview_to_complete.interview_metadata or {}).get("completion_processing", {})
        if lifecycle_status != "in_progress" and not (lifecycle_status == "interrupted" and failure.get("status") == "failed"):
            raise HTTPException(status_code=409, detail="Interview capture is closed")
    if not interview_to_complete or interview_to_complete.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview has not started",
        )

    # An interview without a durable recording cannot be evaluated. Its
    # conversation transcript is still preserved, but the interview is marked as
    # interrupted and receives no evaluation.
    if interview_to_complete.recording is None:
        interrupted = interview_controller.abandon_interview(interview_id)
        if interrupted is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found",
            )
        return CompleteInterviewResponse(
            interview=interrupted,
            evaluation_results=[],
        )

    recording = interview_to_complete.recording
    if lifecycle_status == "in_progress" and not (
        capture_segment_id is None and (recording.capture_config or {}).get("block_finalization") is not None
        and recording.status in {"ready", "partial"} and recording.ended_at is not None
        and not (recording.capture_config or {}).get("resume_attempt")
    ):
        from app.controllers.recording_segments import require_capture_epoch
        require_capture_epoch(db, int(interview_id), capture_segment_id)
    if (recording.status not in {"ready", "partial"}
            or recording.ended_at is None or (recording.duration_ms is None and (recording.capture_config or {}).get('mediaTransport') != 'reusable_blocks_v1')
            or (not recording.segments and not any(asset.status == "ready" for asset in recording.assets))):
        raise HTTPException(status_code=409, detail="Interview media has not been finalized")
    try:
        for asset in recording.assets:
            if asset.status == "ready":
                path = storage.resolve(asset.storage_key)
                if asset.size_bytes <= 0 or path.stat().st_size != asset.size_bytes:
                    raise ValueError("Finalized media size does not match its persisted metadata")
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=409, detail="Finalized interview media is missing") from error

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
            db.flush()

        # Persist the end of the interaction before returning. Evaluation then
        # continues asynchronously so the browser is never held on "Saving".
        from app.multimodal.processing_jobs import stage_processing_job
        from app.models.processing_job import InterviewProcessingJobDB
        pending = db.query(InterviewProcessingJobDB).filter(
            InterviewProcessingJobDB.medical_interview_id == int(interview_id),
            InterviewProcessingJobDB.kind == "completion",
            InterviewProcessingJobDB.status.in_(["queued", "processing"]),
        ).first()
        if pending is not None:
            raise HTTPException(status_code=409, detail="The previous completion attempt is still finishing; retry")
        if lifecycle_status == "interrupted" and (recording.capture_config or {}).get("observation_processing", {}).get("status") == "failed":
            failed_turns = db.query(TurnVideoAnalysisDB).filter(
                TurnVideoAnalysisDB.medical_interview_id == int(interview_id),
                TurnVideoAnalysisDB.status == "failed",
            ).all()
            for turn_job in failed_turns:
                try:
                    source = (turn_job.result or {}).get("block_source")
                    if source:
                        import hashlib
                        from app.models.recording_block import InterviewRecordingBlockDB
                        from app.models.medical_interview import InterviewRecordingSegmentDB
                        from app.multimodal.block_turns import source_identity
                        block = db.get(InterviewRecordingBlockDB, source["block_id"])
                        if block is None or block.recording_id != recording.id:
                            raise ValueError("Block source does not belong to this recording")
                        segment = db.get(InterviewRecordingSegmentDB, block.capture_attempt_id)
                        if source_identity(block, segment, source["window"]) != source["identity"]:
                            raise ValueError("Block source identity changed")
                        with storage.resolve(block.storage_key).open("rb") as original:
                            if hashlib.file_digest(original, "sha256").hexdigest() != block.sha256:
                                raise ValueError("Block original changed")
                    else:
                        storage.resolve(turn_job.storage_key)
                except (FileNotFoundError, ValueError, TypeError, KeyError) as error:
                    raise HTTPException(status_code=409, detail="A failed turn has no recoverable source") from error
                turn_job.status = "queued"
                turn_job.error = None
                turn_job.started_at = None
                turn_job.completed_at = None
            active_pipeline = db.query(InterviewProcessingJobDB).filter(
                InterviewProcessingJobDB.medical_interview_id == int(interview_id),
                InterviewProcessingJobDB.kind == "pipeline",
                InterviewProcessingJobDB.status.in_(["queued", "processing"]),
            ).first()
            if active_pipeline is None:
                stage_processing_job(db, int(interview_id), "pipeline", {"recording_id": recording.id})
            recording.capture_config = {**(recording.capture_config or {}),
                "observation_processing": {"status": "queued", "stage": "queued"}}
        stage_processing_job(db, int(interview_id), "completion", {
            "language": current_user.preferred_language or "en",
            "patient_gender": interview_to_complete.patient_gender,
        })
        if interview_controller.mark_processing(interview_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        processing_interview = interview_controller.get_interview(interview_id)
        return CompleteInterviewResponse(
            interview=processing_interview,
            evaluation_results=[],
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
            detail="Error completing interview"
        )

@router.post("/{interview_id}/abandon", response_model=MedicalInterview)
def abandon_interview(
    interview_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    capture_segment_id: str | None = Header(default=None, alias="X-Capture-Segment"),
    resume_attempt_id: str | None = Header(default=None, alias="X-Resume-Attempt"),
):
    """
    Abandon an interview session.
    
    - **interview_id**: Unique identifier for the interview
    
    Marks the interview as abandoned and sets the end time.
    """
    db.info['capture_wait'] = True
    service = MedicalInterviewController(db)
    
    # Validate access
    if not service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    if not service.validate_interview_ownership(interview_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only the owner can abandon an interview")
    locked = lock_row(db, MedicalInterviewDB, int(interview_id))
    if locked.status == "in_progress":
        from app.controllers.recording_segments import require_capture_epoch
        require_capture_epoch(db, int(interview_id), capture_segment_id, resume_attempt_id, allow_resume=True)
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
def delete_interview(
    interview_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an owned interview, or an organization interview as superuser."""
    query = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id)
    if current_user.role == UserRole.SUPERUSER:
        if current_user.organization_id is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        query = query.join(UserDB, MedicalInterviewDB.user_id == UserDB.id).filter(
            UserDB.organization_id == current_user.organization_id,
            UserDB.role.in_([UserRole.STUDENT, UserRole.TEACHER]),
        )
    else:
        query = query.filter(MedicalInterviewDB.user_id == current_user.id)
    interview = query.first()
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    from app.controllers.administrative_deletion import delete_parent
    delete_parent(db, interview, "interview")
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
    require_organization_staff(current_user, organization_id)
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
    require_organization_staff(current_user, organization_id)
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
    require_organization_staff(current_user, organization_id)
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
    result = interview_controller.get_average_score_for_user(current_user.id, include_text_only=current_user.role == UserRole.SUPERUSER)
    return result
