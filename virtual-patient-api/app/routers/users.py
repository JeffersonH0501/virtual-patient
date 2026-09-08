from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import timedelta
from app.models.user import User, UserCreate, UserUpdate, UserDB, Token
from app.models.organization import OrganizationDB
from app.core.auth import get_current_active_user, get_password_hash, create_access_token, create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.database import get_db

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

@router.post("", response_model=Token, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(func.lower(UserDB.email) == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    organization = db.query(OrganizationDB).filter(
        OrganizationDB.active.is_(True)
    ).order_by(OrganizationDB.id).first()
    if organization is None:
        raise HTTPException(status_code=503, detail="No active organization is available")

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = UserDB(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        hashed_password=hashed_password,
        disabled=False,
        preferred_language=user.preferred_language or "en",
        role=user.role or "student",  # Default to student if not provided
        organization_id=organization.id,
    )
    
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from error
    db.refresh(db_user)

    # Create tokens for the new user (same format as login)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(db_user.id)}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": str(db_user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }

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
    - **first_name**: Given name (optional)
    - **last_name**: Family name (optional)
    - **preferred_language**: New preferred language code (optional)
    Only email, first name, last name, and preferred language can be updated.
    Password, role, and organization membership cannot be changed through this
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
