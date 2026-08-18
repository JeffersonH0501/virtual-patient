from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
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
    # Check if username already exists
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if user.email:
        db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    organization = None
    if user.organization_id is not None:
        organization = db.query(OrganizationDB).filter(
            OrganizationDB.id == user.organization_id,
            OrganizationDB.active.is_(True),
        ).first()
        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization not found or inactive",
            )
    else:
        organization = db.query(OrganizationDB).filter(
            OrganizationDB.active.is_(True)
        ).order_by(OrganizationDB.id).first()
        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No active organization is available",
            )

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = UserDB(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        disabled=False,
        preferred_language=user.preferred_language or "en",
        role=user.role or "student",  # Default to student if not provided
        organization_id=organization.id,
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Create tokens for the new user (same format as login)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": db_user.username})

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
    - **full_name**: New full name (optional)
    - **preferred_language**: New preferred language code (optional)
    - **role**: User role - "teacher" or "student" (optional)
    
    Only provided fields will be updated. Username and password cannot be changed through this endpoint.
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
            UserDB.email == user_update.email,
            UserDB.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Update only provided fields
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    
    return db_user
