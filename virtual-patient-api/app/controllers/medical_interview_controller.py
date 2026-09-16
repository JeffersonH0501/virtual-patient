from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException, status
from app.models.medical_interview import (
    MedicalInterviewDB, MedicalInterview, MedicalInterviewUpdate,
    InterviewStatus, MedicalInterviewComplete, InterviewMessage
)
from app.models.user import UserDB, User
from app.models.clinical_case import ClinicalCase
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.controllers.message_controller import MessageController
from app.controllers.hypothesis_controller import HypothesisController
from app.controllers.progress_summary_controller import ProgressSummaryController

class MedicalInterviewController:
    def __init__(self, db: Session):
        self.db = db
        self.message_service = MessageController(db)
        self.hypothesis_service = HypothesisController(db)
        self.clinical_case_service = ClinicalCaseController(db)
    
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
    
    def get_user_interviews_with_scores(self, user_id: int, status: Optional[InterviewStatus] = None, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all interviews for a user with evaluation scores"""
        from sqlalchemy.orm import joinedload
        
        query = self.db.query(MedicalInterviewDB).options(
            joinedload(MedicalInterviewDB.interview_evaluation)
        ).filter(
            MedicalInterviewDB.user_id == user_id,
            # Only interviews that actually started (passed calibration) are kept in
            # the history. Interviews created but abandoned during calibration have
            # no start_time and must never appear.
            MedicalInterviewDB.start_time.isnot(None),
        )
        
        if status:
            query = query.filter(MedicalInterviewDB.status == status)
        
        interviews = query.order_by(MedicalInterviewDB.start_time.desc()).offset(skip).limit(limit).all()
        
        result = []
        for interview in interviews:
            # Convert to MedicalInterview first
            interview_data = MedicalInterview.from_orm(interview)
            
            # Calculate total_duration if not set but we have start_time and end_time
            if interview_data.total_duration is None and interview.start_time and interview.end_time:
                duration_seconds = int((interview.end_time - interview.start_time).total_seconds())
                interview_data.total_duration = duration_seconds
            
            # Get evaluation score from the relationship
            evaluation_score = None
            if interview.interview_evaluation:
                evaluation_score = interview.interview_evaluation.overall_score
            
            # Create the response with score
            interview_with_score = {
                **interview_data.model_dump(),
                "evaluation_score": evaluation_score
            }
            result.append(interview_with_score)
        
        return result
    
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
            # Calculate total duration when end_time is set
            if interview.start_time:
                interview.total_duration = int((update_data.end_time - interview.start_time).total_seconds())
        
        if update_data.interview_metadata is not None:
            if interview.interview_metadata is None:
                interview.interview_metadata = {}
            interview.interview_metadata.update(update_data.interview_metadata)
        
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
        return self.update_interview(
            interview_id,
            MedicalInterviewUpdate(status=InterviewStatus.PROCESSING),
        )

    def interrupt_processing(self, interview_id: int) -> Optional[MedicalInterview]:
        """Mark an interview as interrupted after a processing failure."""
        return self.update_interview(
            interview_id,
            MedicalInterviewUpdate(
                status=InterviewStatus.INTERRUPTED,
                end_time=datetime.now(timezone.utc),
            ),
        )

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
        
        end_time = datetime.now(timezone.utc)

        completed = self.update_interview(
            interview_id,
            MedicalInterviewUpdate(
                status=InterviewStatus.COMPLETED,
                end_time=end_time
            )
        )

        # Align the stored duration with the per-turn analysis timeline. Turns and
        # the recap are timed against the recording clock (recording.duration_ms,
        # measured by the browser and pause-adjusted), so prefer it as the single
        # source of truth. Fall back to the server wall-clock span only when no
        # recording duration is available.
        recording = interview.recording
        if recording is not None and recording.duration_ms:
            interview.total_duration = int(round(recording.duration_ms / 1000))
            self.db.commit()
            self.db.refresh(interview)
            if completed is not None:
                completed.total_duration = interview.total_duration

        return completed

    def start_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Start a calibrated interview and establish its official clock."""
        interview = self.db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id
        ).first()
        if not interview:
            return None
        if interview.status != InterviewStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only in-progress interviews can be started",
            )
        if interview.start_time is not None:
            return MedicalInterview.from_orm(interview)

        calibration = (interview.interview_metadata or {}).get("calibration") or {}
        if calibration.get("status") != "passed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Technical calibration must pass before the interview starts",
            )

        interview.start_time = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(interview)
        return MedicalInterview.from_orm(interview)
    
    def abandon_interview(self, interview_id: int) -> Optional[MedicalInterview]:
        """Mark an interview as interrupted (student abandoned the session)."""
        return self.update_interview(
            interview_id,
            MedicalInterviewUpdate(
                status=InterviewStatus.INTERRUPTED,
                end_time=datetime.now(timezone.utc)
            )
        )
    
    def validate_interview_access(self, interview_id: int, user_id: int) -> bool:
        """Validate that user has access to this interview"""
        interview = self.db.query(MedicalInterviewDB).filter(
            and_(
                MedicalInterviewDB.id == interview_id,
                MedicalInterviewDB.user_id == user_id
            )
        ).first()
        return interview is not None
    
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
            print(f"Error extracting agent response: {e}")
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
                if hasattr(summary_result, 'dict'):
                    return summary_result.dict()
                elif hasattr(summary_result, '__dict__'):
                    return summary_result.__dict__
                else:
                    return summary_result
                
            except Exception as e:
                print(f"Error extracting summary for response: {e}")
                return None
        
        return None
    
    def prepare_async_database_operations(self, message_service: MessageController, progress_summary_service: ProgressSummaryController, 
                                        interview_id: int, agent_response: str, thread_id: str, 
                                        summary_result: Any, user_message: InterviewMessage = None) -> Dict[str, Any]:
        """Prepare data for async database operations"""
        agent_message_data = {
            "interview_id": interview_id,
            "content": agent_response,
            "message_metadata": {
                "thread_id": thread_id,
                "session_id": thread_id
            }
        }
        
        # Prepare user message data for database if provided
        user_message_data = None
        if user_message:
            user_message_data = {
                "interview_id": interview_id,
                "content": user_message.content,
                "message_metadata": user_message.message_metadata
            }
        
        return {
            "agent_message_data": agent_message_data,
            "user_message_data": user_message_data,
            "summary_result": summary_result,
            "message_service": message_service,
            "progress_summary_service": progress_summary_service
        }
    
    def prepare_async_message_operations(self, message_service: MessageController, 
                                       interview_id: int, agent_response: str, thread_id: str, 
                                       user_message: InterviewMessage = None) -> Dict[str, Any]:
        """Prepare data for async message operations"""
        agent_message_data = {
            "interview_id": interview_id,
            "content": agent_response,
            "message_metadata": {
                "thread_id": thread_id,
                "session_id": thread_id
            }
        }
        
        # Prepare user message data for database if provided
        user_message_data = None
        if user_message:
            user_message_data = {
                "interview_id": interview_id,
                "content": user_message.content,
                "message_metadata": user_message.message_metadata
            }
        
        return {
            "agent_message_data": agent_message_data,
            "user_message_data": user_message_data,
            "message_service": message_service
        }
    
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
                    "role": role,
                    "content": message.content
                })
            elif isinstance(message, dict):
                # Already formatted
                formatted_messages.append(message)
        
        return formatted_messages
    
    def get_interviews_by_organization(self, organization_id: int, current_user: User, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all student interviews (ignoring organization_id parameter). Superusers get all interviews including teacher interviews."""
        from sqlalchemy.orm import joinedload
        from app.models.clinical_case import ClinicalCaseDB
        from app.models.user import UserDB, UserRole
        
        # Query only student interviews (ignoring organization_id parameter)
        query = self.db.query(MedicalInterviewDB).options(
            joinedload(MedicalInterviewDB.interview_evaluation),
            joinedload(MedicalInterviewDB.clinical_case),
            joinedload(MedicalInterviewDB.user),
            joinedload(MedicalInterviewDB.teacher_feedback)
        ).join(ClinicalCaseDB, MedicalInterviewDB.clinical_case_id == ClinicalCaseDB.id).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(MedicalInterviewDB.start_time.isnot(None))
        
        # Filter by role only if user is not a superuser
        if current_user.role != UserRole.SUPERUSER.value:
            query = query.filter(UserDB.role == UserRole.STUDENT.value)
        
        interviews = query.order_by(MedicalInterviewDB.start_time.desc()).offset(skip).limit(limit).all()
        
        result = []
        for interview in interviews:
            # Convert to MedicalInterview first
            interview_data = MedicalInterview.from_orm(interview)
            
            # Calculate total_duration if not set but we have start_time and end_time
            if interview_data.total_duration is None and interview.start_time and interview.end_time:
                duration_seconds = int((interview.end_time - interview.start_time).total_seconds())
                interview_data.total_duration = duration_seconds
            
            # Get evaluation score from the relationship
            evaluation_score = None
            if interview.interview_evaluation:
                evaluation_score = interview.interview_evaluation.overall_score
            
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
                "evaluation_score": evaluation_score,
                "teacher_feedback": teacher_feedback,
                "organization_id": organization_id,  # Keep in response for compatibility
                "clinical_case_title": interview.clinical_case.title if interview.clinical_case else None,
                "user_name": interview.user.name if interview.user else None
            }
            result.append(interview_with_score)
        
        return result
    
    def validate_interview_access(self, interview_id: str, user_id: int) -> bool:
        """Validate if user has access to the interview. Teachers and superusers can access any interview."""
        from app.models.user import UserDB, UserRole
        
        # Get user role
        user = self.db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False
        
        # Teachers and superusers can access any interview
        if user.role == UserRole.TEACHER.value or user.role == UserRole.SUPERUSER.value:
            return True
        
        # Students can only access their own interviews
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        if not interview:
            return False
        
        return interview.user_id == user_id
    
    def count_active_student_conversations_by_organization(self, organization_id: int) -> int:
        """Count the number of students who have active conversations (ignoring organization_id parameter)"""
        from sqlalchemy import distinct
        from app.models.user import UserDB, UserRole
        
        # Query to count distinct students with active interviews (ignoring organization_id parameter)
        count = self.db.query(distinct(MedicalInterviewDB.user_id)).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(
            MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS,
            MedicalInterviewDB.start_time.isnot(None),
            UserDB.role == UserRole.STUDENT.value
        ).count()
        
        return count
    
    def count_completed_student_conversations_by_organization(self, organization_id: int) -> int:
        """Count the number of students who have completed conversations (ignoring organization_id parameter)"""
        from sqlalchemy import distinct
        from app.models.user import UserDB, UserRole
        
        # Query to count distinct students with completed interviews (ignoring organization_id parameter)
        count = self.db.query(distinct(MedicalInterviewDB.user_id)).join(
            UserDB, MedicalInterviewDB.user_id == UserDB.id
        ).filter(
            MedicalInterviewDB.status == InterviewStatus.COMPLETED,
            UserDB.role == UserRole.STUDENT.value
        ).count()
        
        return count
    
    def get_average_score_by_organization(self, organization_id: int) -> Dict[str, Any]:
        """Get the average evaluation score for student conversations only (ignoring organization_id parameter)"""
        from sqlalchemy import func
        from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
        from app.models.user import UserDB, UserRole
        
        # Query to get average score for student interviews only (ignoring
        # organization_id parameter). Only completed interviews count:
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
            UserDB.role == UserRole.STUDENT.value
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
            func.avg(
                func.extract('epoch', MedicalInterviewDB.end_time - MedicalInterviewDB.start_time)
            ).label('average_duration_seconds'),
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

    def get_average_score_for_user(self, user_id: int) -> Dict[str, Any]:
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
            InterviewEvaluationDB.overall_score.isnot(None)
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
