from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, case, func, or_
from fastapi import HTTPException, status
from app.models.medical_interview import (
    MedicalInterviewDB, MedicalInterview, MedicalInterviewUpdate, InterviewMessageDB,
    InterviewStatus, MedicalInterviewComplete, InterviewMessage,
    InterviewRecordingDB, InterviewTurnDB, TurnVideoAnalysisDB, TurnVideoAnalysisStatus,
)
from app.models.user import User, UserDB, UserRole
from app.multimodal.calibration import calibration_passed
from app.models.clinical_case import ClinicalCase
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.controllers.message_controller import MessageController
from app.controllers.hypothesis_controller import HypothesisController
from app.controllers.progress_summary_controller import ProgressSummaryController
from app.controllers.interview_lifecycle import lock_row
from app.core.review_access import can_read_assessments
from app.models.self_rating import SelfRatingDB
from app.models.teacher_grading import TeacherAssignmentDB, TeacherRatingDB
from app.utils.language import resolve_patient_response_language

# Milestones represent completed work, not elapsed time. Evaluation still follows labeling.
REVIEW_PROGRESS_BY_STAGE = {
    "calibration": 5,
    "paraverbal_extraction": 10,
    "paraverbal_preprocessing": 30,
    "nonverbal_extraction": 35,
    "nonverbal_preprocessing": 65,
    "thresholding": 70,
    "labeling": 75,
    "finished": 85,
}

class MedicalInterviewController:
    def __init__(self, db: Session):
        self.db = db
        self.message_service = MessageController(db)
        self.hypothesis_service = HypothesisController(db)
        self.clinical_case_service = ClinicalCaseController(db)

    def _recorded_duration(self, interview: MedicalInterviewDB) -> int | None:
        return self._recorded_durations([interview]).get(interview.id)

    def _recorded_durations(self, interviews) -> dict[int, int | None]:
        if not interviews:
            return {}
        confirmed = case((and_(InterviewRecordingDB.status.in_(["ready", "partial"]),
                              InterviewRecordingDB.ended_at.isnot(None)), InterviewRecordingDB.duration_ms))
        rows = self.db.query(MedicalInterviewDB.id, func.coalesce(confirmed, func.max(InterviewTurnDB.end_ms))).outerjoin(
            InterviewRecordingDB, InterviewRecordingDB.medical_interview_id == MedicalInterviewDB.id,
        ).outerjoin(InterviewTurnDB, InterviewTurnDB.medical_interview_id == MedicalInterviewDB.id).filter(
            MedicalInterviewDB.id.in_([interview.id for interview in interviews]),
        ).group_by(MedicalInterviewDB.id, InterviewRecordingDB.status, InterviewRecordingDB.ended_at,
                   InterviewRecordingDB.duration_ms).all()
        result = {identifier: duration // 1000 if duration is not None else None for identifier, duration in rows}
        from app.models.recording_block import InterviewRecordingBlockDB
        block_durations = self.db.query(InterviewRecordingDB.medical_interview_id, func.sum(InterviewRecordingBlockDB.duration_ms)).outerjoin(
            InterviewRecordingBlockDB, InterviewRecordingBlockDB.recording_id == InterviewRecordingDB.id).filter(
            InterviewRecordingDB.medical_interview_id.in_([interview.id for interview in interviews]),
            InterviewRecordingDB.capture_config['mediaTransport'].as_string() == 'reusable_blocks_v1').group_by(
            InterviewRecordingDB.medical_interview_id).all()
        for identifier, duration in block_durations:
            result[identifier] = int(duration // 1000) if duration is not None else None
        return result
    
    def create_interview(self, user_id: int, clinical_case_id: int, interview_metadata: Optional[Dict[str, Any]] = None,
                        patient_name: Optional[str] = None, patient_photo: Optional[str] = None,
                        patient_gender: Optional[str] = None, personality_id: Optional[int] = None) -> MedicalInterview:
        """Create a new medical interview"""
        # Validate that the clinical case exists
        clinical_case = self.clinical_case_service.get_clinical_case(clinical_case_id)
        if not clinical_case:
            raise ValueError(f"Clinical case with ID {clinical_case_id} not found")
        
        # If gender restriction is set, use it and ignore any provided patient_gender
        final_patient_gender = patient_gender
        if clinical_case.gender_restriction:
            final_patient_gender = clinical_case.gender_restriction
        
        # Auto-select patient name from clinical case based on gender if not provided
        final_patient_name = patient_name
        final_patient_photo = patient_photo
        
        if final_patient_gender and not patient_name:
            if final_patient_gender.lower() == 'female':
                final_patient_name = clinical_case.female_name
                final_patient_photo = clinical_case.female_photo
            elif final_patient_gender.lower() == 'male':
                final_patient_name = clinical_case.male_name
                final_patient_photo = clinical_case.male_photo
        
        interview = MedicalInterviewDB(
            user_id=user_id,
            clinical_case_id=clinical_case_id,
            status=InterviewStatus.IN_PROGRESS,
            interview_metadata=interview_metadata or {},
            start_time=None,
            patient_name=final_patient_name,
            patient_photo=final_patient_photo,
            patient_gender=final_patient_gender,
            personality_id=personality_id
        )

        self.db.add(interview)
        self.db.commit()
        self.db.refresh(interview)

        return MedicalInterview.from_orm(interview)

    def get_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Get interview by ID"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        return MedicalInterview.from_orm(interview) if interview else None
    
    def get_interview_complete(self, interview_id: int) -> Optional[MedicalInterviewComplete]:
        """Get interview with all related data"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return None
        
        return MedicalInterviewComplete.from_orm(interview)
    
    def get_user_interviews(self, user_id: str, status: Optional[InterviewStatus] = None) -> List[MedicalInterview]:
        """Get all interviews for a user"""
        query = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.user_id == user_id)
        
        if status:
            query = query.filter(MedicalInterviewDB.status == status)
        
        interviews = query.order_by(MedicalInterviewDB.start_time.desc()).all()
        return [MedicalInterview.from_orm(interview) for interview in interviews]

    def get_active_started_interview(self, user_id: int) -> Optional[MedicalInterviewDB]:
        """Return the user's in-progress interview, if any.

        An interview is considered in progress once it has started (start_time is
        set after calibration) and has not been completed or interrupted. A
        student may only have one such interview at a time.
        """
        return self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.user_id == user_id,
            MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS,
            MedicalInterviewDB.start_time.isnot(None),
        ).order_by(MedicalInterviewDB.start_time.desc()).first()
    
    def get_user_interviews_with_scores(self, user_id: int, status: Optional[InterviewStatus] = None, skip: int = 0, limit: int = 100, *, include_assigned: bool = False) -> List[Dict[str, Any]]:
        """Get all interviews for a user with evaluation scores"""
        from sqlalchemy.orm import joinedload
        
        score_relation = MedicalInterviewDB.multimodal_interview_evaluation
        actor = self.db.get(UserDB, user_id)
        visibility = MedicalInterviewDB.user_id == user_id
        if include_assigned and actor and actor.role == UserRole.TEACHER and actor.organization_id is not None:
            assigned = self.db.query(TeacherAssignmentDB.id).filter(
                TeacherAssignmentDB.interview_id == MedicalInterviewDB.id,
                TeacherAssignmentDB.teacher_id == user_id,
            ).exists()
            same_organization = MedicalInterviewDB.user_id.in_(
                self.db.query(UserDB.id).filter(UserDB.organization_id == actor.organization_id)
            )
            visibility = or_(visibility, and_(assigned, same_organization))
        query = self.db.query(MedicalInterviewDB).options(joinedload(score_relation)).filter(
            visibility,
            # Only interviews that actually started (passed calibration) are kept in
            # the history. Interviews created but abandoned during calibration have
            # no start_time and must never appear.
            MedicalInterviewDB.start_time.isnot(None),
        )
        
        if status:
            query = query.filter(MedicalInterviewDB.status == status)
        
        interviews = query.order_by(MedicalInterviewDB.start_time.desc(), MedicalInterviewDB.id.desc()).offset(skip).limit(limit).all()

        interview_ids = [interview.id for interview in interviews]
        self_ratings = {rating.interview_id: rating for rating in self.db.query(SelfRatingDB).filter(
            SelfRatingDB.interview_id.in_(interview_ids),
            SelfRatingDB.interview_id.in_(self.db.query(MedicalInterviewDB.id).filter(MedicalInterviewDB.user_id == user_id)),
        ).all()} if interview_ids else {}
        assigned_ratings = dict(self.db.query(TeacherAssignmentDB.interview_id, TeacherRatingDB).outerjoin(
            TeacherRatingDB, TeacherRatingDB.assignment_id == TeacherAssignmentDB.id,
        ).filter(TeacherAssignmentDB.teacher_id == user_id, TeacherAssignmentDB.interview_id.in_(interview_ids)).all()) if interview_ids else {}
        progress_by_interview: Dict[int, Dict[str, int]] = {}
        if interview_ids:
            progress_rows = self.db.query(
                TurnVideoAnalysisDB.medical_interview_id,
                func.count(TurnVideoAnalysisDB.id),
                func.sum(case(
                    (TurnVideoAnalysisDB.status == TurnVideoAnalysisStatus.COMPLETED.value, 1),
                    else_=0,
                )),
            ).filter(
                TurnVideoAnalysisDB.medical_interview_id.in_(interview_ids),
            ).group_by(TurnVideoAnalysisDB.medical_interview_id).all()
            for interview_id, total, completed in progress_rows:
                completed_count = int(completed or 0)
                total_count = int(total or 0)
                progress_by_interview[interview_id] = {
                    "completed": completed_count,
                    "total": total_count,
                    "percentage": round((completed_count / total_count) * 100) if total_count else 0,
                }
        
        review_progress = self._get_review_progress(interviews)
        durations = self._recorded_durations(interviews)
        result = []
        for interview in interviews:
            # Convert to MedicalInterview first
            interview_data = MedicalInterview.from_orm(interview)
            
            
            # Get evaluation score from the relationship
            evaluation = getattr(interview, score_relation.key)
            is_assigned = interview.user_id != user_id
            rating = assigned_ratings.get(interview.id) if is_assigned else self_ratings.get(interview.id)
            manual_rating_status = "submitted" if rating and rating.submitted_at else "in_progress" if rating else "pending"
            evaluation_score = evaluation.overall_score if evaluation and can_read_assessments(self.db, interview, actor) else None
            
            # Create the response with score
            interview_with_score = {
                **interview_data.model_dump(),
                "total_duration": durations.get(interview.id),
                "interview_metadata": {} if is_assigned else interview_data.interview_metadata,
                "evaluation_score": evaluation_score,
                "is_assigned": is_assigned,
                "manual_rating_status": manual_rating_status,
                "analysis_progress": progress_by_interview.get(interview.id),
                "review_progress": review_progress.get(interview.id),
            }
            result.append(interview_with_score)
        
        return result

    def _get_review_progress(self, interviews: List[MedicalInterviewDB]) -> Dict[int, int]:
        progress = {
            interview.id: 0 for interview in interviews
            if interview.status == InterviewStatus.PROCESSING
        }
        if progress:
            recordings = self.db.query(
                InterviewRecordingDB.medical_interview_id,
                InterviewRecordingDB.capture_config,
            ).filter(InterviewRecordingDB.medical_interview_id.in_(progress)).all()
            for interview_id, config in recordings:
                processing = (config or {}).get("observation_processing") or {}
                if processing.get("status") == "failed":
                    progress.pop(interview_id)
                else:
                    progress[interview_id] = REVIEW_PROGRESS_BY_STAGE.get(processing.get("stage"), 0)
        return progress
    
    def update_interview(self, interview_id: int, update_data: MedicalInterviewUpdate) -> Optional[MedicalInterview]:
        """Update interview status and interview_metadata"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return None
        
        # Update fields
        if update_data.status is not None:
            interview.status = update_data.status
        
        if update_data.end_time is not None:
            interview.end_time = update_data.end_time
            interview.total_duration = self._recorded_duration(interview)
        
        if update_data.interview_metadata is not None:
            interview.interview_metadata = {**(interview.interview_metadata or {}), **update_data.interview_metadata}
        
        self.db.commit()
        self.db.refresh(interview)
        
        return MedicalInterview.from_orm(interview)
    
    def mark_processing(self, interview_id: int) -> Optional[MedicalInterview]:
        """Mark an interview as processing its evaluation and feedback.

        The interaction with the virtual patient has ended and the collected
        information is being processed. This is the transient state between
        IN_PROGRESS and COMPLETED.
        """
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return None
        if interview.start_time is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The interview has not started",
            )
        interview.status = InterviewStatus.PROCESSING
        if interview.end_time is None:
            interview.end_time = datetime.now(timezone.utc)
        interview.total_duration = self._recorded_duration(interview)
        metadata = dict(interview.interview_metadata or {})
        metadata["completion_processing"] = {"status": "queued"}
        interview.interview_metadata = metadata
        self.db.commit()
        self.db.refresh(interview)
        return MedicalInterview.model_validate(interview)

    def interrupt_processing(self, interview_id: int) -> Optional[MedicalInterview]:
        """Mark an interview as interrupted after a processing failure."""
        interview = lock_row(self.db, MedicalInterviewDB, interview_id)
        if interview is None:
            return None
        if interview.status != InterviewStatus.PROCESSING:
            return MedicalInterview.model_validate(interview)
        interview.status = InterviewStatus.INTERRUPTED
        interview.interview_metadata = {**(interview.interview_metadata or {}),
            "completion_processing": {"status": "failed", "error_code": "completion-processing-failed"}}
        self.db.commit()
        self.db.refresh(interview)
        return MedicalInterview.model_validate(interview)

    def complete_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Complete an interview"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return None
        if interview.start_time is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The interview has not started",
            )
        
        if interview.status == InterviewStatus.COMPLETED:
            return MedicalInterview.model_validate(interview)
        if interview.status != InterviewStatus.PROCESSING:
            raise HTTPException(status_code=409, detail="Only a processing interview can complete")
        interview.status = InterviewStatus.COMPLETED
        interview.interview_metadata = {**(interview.interview_metadata or {}),
            "completion_processing": {"status": "complete"}}
        self.db.commit()
        self.db.refresh(interview)
        return MedicalInterview.model_validate(interview)

    def start_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Start a calibrated interview and establish its official clock."""
        interview = self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id
        ).first()
        if not interview:
            return None
        lock_row(self.db, UserDB, interview.user_id)
        interview = lock_row(self.db, MedicalInterviewDB, interview_id)
        if interview is None:
            return None
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only in-progress interviews can be started",
            )
        if interview.start_time is not None:
            return MedicalInterview.from_orm(interview)
        other_active = self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.user_id == interview.user_id,
            MedicalInterviewDB.id != interview.id,
            MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS,
            MedicalInterviewDB.start_time.isnot(None),
        ).first()
        if other_active is not None:
            raise HTTPException(status_code=409, detail="You already have an interview in progress")

        # The calibration draft is persisted into ``interview_metadata.calibration``
        # before start. The central ``calibration_passed`` accessor checks the
        # stored block is ``passed`` and carries a valid personal baseline, so
        # the gate never reaches into the metadata dict directly.
        if not calibration_passed(interview):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A passed multimodal calibration must be saved before the interview starts",
            )

        interview.start_time = datetime.now(timezone.utc)
        language = resolve_patient_response_language(interview.interview_metadata)
        self.message_service.create_patient_message(
            interview_id,
            "Hola, mucho gusto." if language == "es" else "Hello, nice to meet you.",
            message_metadata={"opening": True},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(interview)
        return MedicalInterview.from_orm(interview)
    
    def abandon_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Mark an interview as interrupted (student abandoned the session)."""
        interview = lock_row(self.db, MedicalInterviewDB, interview_id)
        if interview is None:
            return None
        if interview.status == InterviewStatus.INTERRUPTED:
            return MedicalInterview.from_orm(interview)
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(status_code=409, detail="A frozen interview cannot be abandoned")
        recording = interview.recording
        if recording is not None and (recording.segments or (recording.capture_config or {}).get('mediaTransport') == 'reusable_blocks_v1'):
            from app.controllers.recording_segments import pending_patient_message, seal_segment
            pending_message = pending_patient_message(self.db, interview.id)
            for segment in recording.segments:
                seal_segment(self.db, segment, pending_message)
            recording.duration_ms = sum(segment.duration_ms for segment in recording.segments)
            if (recording.capture_config or {}).get('mediaTransport') == 'reusable_blocks_v1':
                from app.models.recording_block import InterviewRecordingBlockDB
                blocks = self.db.query(InterviewRecordingBlockDB).filter_by(recording_id=recording.id).all()
                confirmed = [block.duration_ms for block in blocks if block.duration_ms is not None]
                recording.duration_ms = sum(confirmed) if confirmed else None
                covered = {value for block in blocks for key in ('student_message_id', 'patient_message_id')
                           if (value := block.block_metadata.get(key)) is not None}
                messages = {item[0] for item in self.db.query(InterviewMessageDB.id).filter_by(interview_id=interview.id)}
                previous_gaps = set((interview.interview_metadata or {}).get('missing_evidence_message_ids', []))
                interview.interview_metadata = {**(interview.interview_metadata or {}), 'missing_evidence_message_ids': sorted(previous_gaps | (messages - covered))}
            recording.ended_at = datetime.now(timezone.utc)
            recording.status = "partial"
            recording.capture_config = {key: value for key, value in (recording.capture_config or {}).items()
                                        if key != "resume_attempt"}
        return self.update_interview(
            interview_id,
            MedicalInterviewUpdate(
                status=InterviewStatus.INTERRUPTED,
                end_time=datetime.now(timezone.utc)
            )
        )
    
    def get_interview_context(self, interview_id: int) -> Dict[str, Any]:
        """Get complete interview context for GPT agent"""
        interview = self.get_interview_complete(interview_id)
        if not interview:
            return {}
        
        return {
            "interview": interview,
            "messages": interview.messages,
            "hypotheses": interview.hypotheses,
            "session_notes": interview.session_notes,
            "progress_summary": interview.progress_summary,
            "clinical_case": interview.clinical_case
        }
    
    def validate_interview_access_with_case(self, interview_id: int, current_user: User) -> Tuple[MedicalInterview, ClinicalCase]:
        """Validate access and return interview with clinical case"""
        # Validate access
        if not self.validate_interview_access(interview_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this interview"
            )

        # Validate interview exists and is in progress
        interview = self.get_interview(interview_id)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interview is not in progress"
            )
        if interview.start_time is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The interview has not started",
            )

        # Get the complete clinical case with all medical details
        clinical_case = self.clinical_case_service.get_clinical_case(interview.clinical_case_id)
        if not clinical_case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clinical case with ID {interview.clinical_case_id} not found"
            )    

        return interview, clinical_case
    
    def extract_agent_response(self, workflow_result: Dict[str, Any]) -> Optional[str]:
        """Helper to extract the agent response (last message content) from workflow_result."""
        try:
            messages = workflow_result.get("interview_result", {}).get("messages", [])
            if messages:
                last_message = messages[-1]
                if isinstance(last_message, dict):
                    return last_message.get("content")
                return getattr(last_message, "content", None)
        except Exception as e:
            pass
        return None
    
    def create_message_object(self, interview_id: int, content: str, sender_type: str, 
                            message_metadata: Dict[str, Any] = None) -> InterviewMessage:
        """Create a temporary message object for any sender type"""
        if message_metadata is None:
            message_metadata = {}
            
        return InterviewMessage(
            id=0,  # Temporary ID
            interview_id=interview_id,
            content=content,
            sender_type=sender_type,
            message_metadata=message_metadata,
            created_at=datetime.now()
        )
    
    def create_agent_message_object(self, interview_id: int, agent_response: str, thread_id: str) -> InterviewMessage:
        """Create a temporary message object for the agent response"""
        message_metadata = {
            "thread_id": thread_id,
            "session_id": thread_id  # Use thread_id as session_id for consistency
        }
        
        return self.create_message_object(
            interview_id=interview_id,
            content=agent_response,
            sender_type="chatbot",
            message_metadata=message_metadata
        )
    
    def extract_summary_for_response(self, workflow_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract translated summary for response from workflow result"""
        summary_result = workflow_result.get("translated_summary")
        
        if summary_result:
            try:
                # Convert summary_result to dict for response
                if hasattr(summary_result, 'model_dump'):
                    return summary_result.model_dump()
                elif hasattr(summary_result, '__dict__'):
                    return summary_result.__dict__
                else:
                    return summary_result
                
            except Exception as e:
                return None
        
        return None
    
    
    
    def get_interview_evaluation_data(self, interview_id: int) -> Dict[str, Any]:
        """Get all data needed for interview evaluation"""
        # Get complete interview context
        interview_context = self.get_interview_context(interview_id)
        
        if not interview_context:
            raise ValueError(f"Interview {interview_id} not found or has no context")
        
        # Get messages for evaluation
        messages = interview_context.get("messages", [])
        
        # Get progress summary
        progress_summary = interview_context.get("progress_summary")
        
        # Get clinical case
        clinical_case = interview_context.get("clinical_case")
        
        # Get hypotheses for hypothesis evaluation
        hypotheses = self.hypothesis_service.get_interview_hypotheses(interview_id)
        
        return {
            "messages": messages,
            "progress_summary": progress_summary,
            "clinical_case": clinical_case,
            "interview": interview_context.get("interview"),
            "hypotheses": hypotheses
        }
    
    def format_messages_for_evaluation(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Format messages for evaluation agent"""
        formatted_messages = []
        
        for message in messages:
            if hasattr(message, 'sender_type') and hasattr(message, 'content'):
                # Convert to evaluation format
                role = "user" if message.sender_type == "user" else "assistant"
                formatted_messages.append({
                    "id": message.id,
                    "role": role,
                    "content": message.content
                })
            elif isinstance(message, dict):
                # Already formatted
                formatted_messages.append(message)
        
        return formatted_messages
    
    def organization_interviews_query(self, organization_id: int, current_user: User):
        """Use the same role and organization scope for rows and interview counts."""
        from sqlalchemy.orm import joinedload
        from app.models.clinical_case import ClinicalCaseDB
        from app.models.user import UserDB, UserRole

        # Scope the query before applying role filters and pagination.
        query = self.db.query(MedicalInterviewDB).options(
            joinedload(MedicalInterviewDB.multimodal_interview_evaluation),
            joinedload(MedicalInterviewDB.clinical_case),
            joinedload(MedicalInterviewDB.user),
            joinedload(MedicalInterviewDB.teacher_feedback)
        ).join(ClinicalCaseDB, MedicalInterviewDB.clinical_case_id == ClinicalCaseDB.id).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(MedicalInterviewDB.start_time.isnot(None), UserDB.organization_id == organization_id)
        
        # Filter by role only if user is not a superuser
        if current_user.role != UserRole.SUPERUSER.value:
            query = query.filter(UserDB.role == UserRole.STUDENT.value)
        
        return query

    def count_organization_interviews(self, organization_id: int, current_user: User) -> int:
        return self.organization_interviews_query(organization_id, current_user).count()

    def get_organization_interview_counts(self, organization_id: int, current_user: User):
        """Count interviews, including multiple interviews owned by the same person."""
        query = self.organization_interviews_query(organization_id, current_user)
        return {
            "active_interviews_count": query.filter(MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS).count(),
            "completed_interviews_count": query.filter(MedicalInterviewDB.status == InterviewStatus.COMPLETED).count(),
        }

    def get_interviews_by_organization(self, organization_id: int, current_user: User, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """List organization interviews; superusers may also review teachers."""
        query = self.organization_interviews_query(organization_id, current_user)

        interviews = query.order_by(MedicalInterviewDB.start_time.desc()).offset(skip).limit(limit).all()
        review_progress = self._get_review_progress(interviews)
        durations = self._recorded_durations(interviews)
        
        result = []
        for interview in interviews:
            # Convert to MedicalInterview first
            interview_data = MedicalInterview.from_orm(interview)
            
            
            # Get evaluation score from the relationship
            evaluation = interview.multimodal_interview_evaluation
            evaluation_score = evaluation.overall_score if evaluation and can_read_assessments(self.db, interview, current_user) else None

            # Get teacher feedback data
            teacher_feedback = []
            if interview.teacher_feedback:
                for feedback in interview.teacher_feedback:
                    teacher_feedback.append({
                        "id": feedback.id,
                        "feedback": feedback.feedback,
                        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
                        "reviewed_by_you": feedback.teacher_id == current_user.id
                    })
            
            # Create the response with score and additional organization context
            interview_with_score = {
                **interview_data.model_dump(),
                "total_duration": durations.get(interview.id),
                "evaluation_score": evaluation_score,
                "teacher_feedback": teacher_feedback,
                "review_progress": review_progress.get(interview.id),
                "organization_id": organization_id,  # Keep in response for compatibility
                "clinical_case_title": interview.clinical_case.title if interview.clinical_case else None,
                "owner_role": interview.user.role if interview.user else None,
                "user_name": interview.user.name if interview.user else None
            }
            result.append(interview_with_score)
        
        return result
    
    def validate_interview_access(self, interview_id: str, user_id: int) -> bool:
        """Allow owners and authorized staff within the owner's organization."""
        from app.models.user import UserDB, UserRole
        
        # Get user role
        user = self.db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False
        
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return False
        
        if interview.user_id == user_id:
            return True
        from app.core.review_access import can_replay
        return can_replay(self.db, interview, user)

    def validate_interview_ownership(self, interview_id: int, user_id: int) -> bool:
        """Mutations require ownership, independently of staff read access."""
        return self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id, MedicalInterviewDB.user_id == user_id,
        ).first() is not None
    
    def count_active_student_conversations_by_organization(self, organization_id: int) -> int:
        """Count students with active interviews in this organization."""
        from sqlalchemy import distinct
        from app.models.user import UserDB, UserRole
        
        # Count distinct students within the organization.
        count = self.db.query(distinct(MedicalInterviewDB.user_id)).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(
            MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS,
            MedicalInterviewDB.start_time.isnot(None),
            UserDB.role == UserRole.STUDENT.value,
            UserDB.organization_id == organization_id,
        ).count()
        
        return count
    
    def count_completed_student_conversations_by_organization(self, organization_id: int) -> int:
        """Count students with completed interviews in this organization."""
        from sqlalchemy import distinct
        from app.models.user import UserDB, UserRole
        
        # Count distinct students within the organization.
        count = self.db.query(distinct(MedicalInterviewDB.user_id)).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(
            MedicalInterviewDB.status == InterviewStatus.COMPLETED,
            UserDB.role == UserRole.STUDENT.value,
            UserDB.organization_id == organization_id,
        ).count()
        
        return count
    
    def get_average_score_by_organization(self, organization_id: int) -> Dict[str, Any]:
        """Average the textual control for completed organization interviews."""
        from sqlalchemy import func
        from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
        from app.models.user import UserDB, UserRole
        
        # Only completed interviews in the organization count:
        # interrupted interviews carry no evaluation and must never contribute
        # to the overall score.
        result = self.db.query(
            func.avg(InterviewEvaluationDB.overall_score).label('average_score'),
            func.count(InterviewEvaluationDB.id).label('total_evaluations')
        ).join(
            MedicalInterviewDB, InterviewEvaluationDB.medical_interview_id == MedicalInterviewDB.id
        ).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(
            MedicalInterviewDB.status == InterviewStatus.COMPLETED,
            InterviewEvaluationDB.overall_score.isnot(None),
            InterviewEvaluationDB.evaluation_condition == "TEXT_ONLY",
            UserDB.role == UserRole.STUDENT.value,
            UserDB.organization_id == organization_id,
        ).first()
        
        if result and result.average_score is not None:
            return {
                "organization_id": organization_id,  # Keep in response for compatibility
                "average_score": round(float(result.average_score), 2),
                "total_evaluations": result.total_evaluations,
                "has_data": True
            }
        else:
            return {
                "organization_id": organization_id,  # Keep in response for compatibility
                "average_score": None,
                "total_evaluations": 0,
                "has_data": False
            }

    def count_completed_cases_for_user(self, user_id: int) -> int:
        """Count the number of completed cases for a specific user"""
        from app.models.medical_interview.enums import InterviewStatus
        
        count = self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.user_id == user_id,
            MedicalInterviewDB.status == InterviewStatus.COMPLETED
        ).count()
        
        return count

    def get_average_duration_for_user(self, user_id: int) -> Dict[str, Any]:
        """Get the average duration of completed cases for a specific user"""
        from app.models.medical_interview.enums import InterviewStatus
        from sqlalchemy import func
        
        # Query to get average duration for completed interviews of the user
        result = self.db.query(
            func.avg(MedicalInterviewDB.total_duration).label('average_duration_seconds'),
            func.count(MedicalInterviewDB.id).label('total_completed_cases')
        ).filter(
            MedicalInterviewDB.user_id == user_id,
            MedicalInterviewDB.status == InterviewStatus.COMPLETED,
            MedicalInterviewDB.end_time.isnot(None),
            MedicalInterviewDB.start_time.isnot(None)
        ).first()
        
        if result and result.average_duration_seconds is not None:
            return {
                "user_id": user_id,
                "average_duration_seconds": round(float(result.average_duration_seconds), 2),
                "total_completed_cases": result.total_completed_cases,
                "has_data": True
            }
        else:
            return {
                "user_id": user_id,
                "average_duration_seconds": None,
                "total_completed_cases": 0,
                "has_data": False
            }

    def get_average_score_for_user(self, user_id: int, *, include_text_only: bool = False) -> Dict[str, Any]:
        """Get the average evaluation score for a specific user's conversations"""
        from app.models.medical_interview.enums import InterviewStatus
        from sqlalchemy import func
        from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
        
        # Query to get average score for user's interviews. Only completed
        # interviews count: interrupted interviews carry no evaluation and must
        # never contribute to the overall score.
        result = self.db.query(
            func.avg(InterviewEvaluationDB.overall_score).label('average_score'),
            func.count(InterviewEvaluationDB.id).label('total_evaluations')
        ).join(
            MedicalInterviewDB, InterviewEvaluationDB.medical_interview_id == MedicalInterviewDB.id
        ).filter(
            MedicalInterviewDB.user_id == user_id,
            MedicalInterviewDB.status == InterviewStatus.COMPLETED,
            InterviewEvaluationDB.overall_score.isnot(None),
            InterviewEvaluationDB.evaluation_condition == ("TEXT_ONLY" if include_text_only else "TEXT_PLUS_MULTIMODAL"),
            True if include_text_only else self.db.query(SelfRatingDB).filter(
                SelfRatingDB.interview_id == MedicalInterviewDB.id, SelfRatingDB.submitted_at.isnot(None),
            ).exists(),
        ).first()
        
        if result and result.average_score is not None:
            return {
                "user_id": user_id,
                "average_score": round(float(result.average_score), 2),
                "total_evaluations": result.total_evaluations,
                "has_data": True
            }
        else:
            return {
                "user_id": user_id,
                "average_score": None,
                "total_evaluations": 0,
                "has_data": False
            }
