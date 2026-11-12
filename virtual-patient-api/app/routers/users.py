from fastapi import APIRouter, Depends, HTTPException, status, Response
from app.core.media_cookie import set_media_cookie
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import timedelta
from app.models.user import User, UserCreate, AdminUserCreate, AdminUserUpdate, UserUpdate, UserDB, UserRole, Token
from app.core.auth import get_current_active_user, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, require_admin
from app.core.database import get_db
from app.core.captcha import require_captcha

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

def persist_user(user: UserCreate, db: Session):
    if db.query(UserDB).filter(func.lower(UserDB.email) == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = UserDB(
        email=user.email,
        name=user.name,
        hashed_password=hashed_password,
        disabled=False,
        preferred_language=user.preferred_language or "es",
        role=user.role,
        semester_range=user.semester_range if user.role == UserRole.STUDENT else None,
        university=user.university if user.role == UserRole.STUDENT else None,
    )
    
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from error
    db.refresh(db_user)
    return db_user


@router.post("", response_model=Token, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_captcha)])
def create_user(user: UserCreate, response: Response, db: Session = Depends(get_db)):
    if user.role == UserRole.STUDENT and (not user.semester_range or not user.university):
        raise HTTPException(status_code=422, detail="Students must provide semester and university")
    db_user = persist_user(user, db)

    # Create tokens for the new user (same format as login)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(db_user.id)}, expires_delta=access_token_expires
    )
    set_media_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }


@router.get("/admin", response_model=list[User])
async def list_managed_users(
    response: Response,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    offset: int = 0,
    limit: int = 100,
):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    query = db.query(UserDB).filter(
        UserDB.role.in_([UserRole.STUDENT, UserRole.DOCTOR]),
    )
    response.headers["X-Total-Count"] = str(query.count())
    return query.order_by(UserDB.id).offset(offset).limit(limit).all()


def managed_account(db: Session, current_user: User, user_id: int):
    account = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.role.in_([UserRole.STUDENT, UserRole.DOCTOR]),
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="User not found")
    return account


@router.get("/admin/activity")
def managed_activity(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.models.medical_interview import MedicalInterviewDB
    from app.models.doctor_grading import DoctorAssignmentDB
    from app.models.perception_survey import PerceptionSurveyDB
    accounts = db.query(UserDB.id, UserDB.role).filter(
        UserDB.role.in_([UserRole.STUDENT, UserRole.DOCTOR]),
    ).all()
    ids = [account.id for account in accounts]
    own = {row[0] for row in db.query(MedicalInterviewDB.user_id).filter(
        MedicalInterviewDB.user_id.in_(ids), MedicalInterviewDB.start_time.isnot(None),
    ).distinct()}
    assigned = {row[0] for row in db.query(DoctorAssignmentDB.doctor_id).join(
        MedicalInterviewDB, MedicalInterviewDB.id == DoctorAssignmentDB.interview_id,
    ).join(UserDB, UserDB.id == MedicalInterviewDB.user_id).filter(
        DoctorAssignmentDB.doctor_id.in_(ids),
        MedicalInterviewDB.start_time.isnot(None),
    ).distinct()}
    submitted = {row[0] for row in db.query(PerceptionSurveyDB.user_id).filter(
        PerceptionSurveyDB.user_id.in_(ids), PerceptionSurveyDB.status == "SUBMITTED",
    ).all()}
    return [{"user_id": account.id, "has_interviews": account.id in own or (account.role == UserRole.DOCTOR and account.id in assigned),
             "has_submitted_survey": account.id in submitted} for account in accounts]


@router.get("/admin/{user_id}/interviews")
def managed_interviews(user_id: int, skip: int = 0, limit: int = 100,
                       db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.controllers.medical_interview_controller import MedicalInterviewController
    from app.routers.medical_interviews import translate_interview_personality
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    account = managed_account(db, current_user, user_id)
    interviews = MedicalInterviewController(db).get_user_interviews_with_scores(
        user_id=account.id, skip=skip, limit=limit, include_assigned=account.role == UserRole.DOCTOR,
    )
    for interview in interviews:
        translate_interview_personality(interview, current_user.preferred_language or "en")
    return interviews


@router.get("/admin/{user_id}/survey")
def managed_survey(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.models.perception_survey import PerceptionSurveyDB
    from app.routers.perception_survey import serialize
    account = managed_account(db, current_user, user_id)
    record = db.get(PerceptionSurveyDB, account.id)
    if record is None or record.status != "SUBMITTED":
        raise HTTPException(status_code=404, detail="Submitted survey not found")
    return serialize(record, True)


@router.post("/admin", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_managed_user(
    user: AdminUserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return persist_user(user, db)

@router.patch("/admin/{user_id}", response_model=User)
async def update_managed_user(
    user_id: int,
    user_update: AdminUserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.role.in_([UserRole.STUDENT, UserRole.DOCTOR]),
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = user_update.model_dump(exclude_unset=True)
    if changes.get("role", account.role) != UserRole.STUDENT and any(
        changes.get(field) is not None for field in ("semester_range", "university")
    ):
        raise HTTPException(status_code=422, detail="Academic fields are only available for students")
    if "email" in changes and db.query(UserDB).filter(
        func.lower(UserDB.email) == changes["email"], UserDB.id != user_id,
    ).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if "password" in changes:
        account.hashed_password = get_password_hash(changes.pop("password"))
    for field, value in changes.items():
        setattr(account, field, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from error
    db.refresh(account)
    return account


@router.get("/admin/doctors")
def assignable_doctors(offset: int = 0, limit: int = 5, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(422, "Invalid pagination")
    query = db.query(UserDB).filter(UserDB.role == UserRole.DOCTOR, UserDB.disabled == False)
    return {"users": [User.model_validate(item) for item in query.order_by(UserDB.id).offset(offset).limit(limit).all()], "total": query.count()}


@router.delete("/admin/{user_id}", status_code=204)
def delete_managed_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.controllers.administrative_deletion import delete_parent
    account = db.query(UserDB).filter(UserDB.id == user_id, UserDB.role.in_([UserRole.STUDENT, UserRole.DOCTOR])).with_for_update().first()
    if not account:
        raise HTTPException(404, "User not found")
    delete_parent(db, account, "user")


@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@router.post("/me", response_model=User)
async def update_user_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update the current user's profile information.
    
    - **email**: New email address (optional)
    - **name**: Display name (optional)
    - **preferred_language**: New preferred language code (optional)
    Only email, name, and preferred language can be updated.
    Password and role cannot be changed through this
    endpoint.
    """
    # Get the user from database
    db_user = db.query(UserDB).filter(UserDB.id == current_user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if email is being updated and if it already exists
    if user_update.email and user_update.email != db_user.email:
        existing_user = db.query(UserDB).filter(
            func.lower(UserDB.email) == user_update.email,
            UserDB.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Update only provided fields
    update_data = user_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from error
    db.refresh(db_user)
    
    return db_user
