from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import ConfigDict, EmailStr
from jose import JWTError, jwt
from app.models.user import User, Token, EmailIdentity
from app.core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_active_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.core.database import get_db

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

class TokenRequest(EmailIdentity):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str

@router.post("/token", response_model=Token)
async def login_for_access_token(
    token_request: TokenRequest,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, token_request.email, token_request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    # In a real application, you might want to blacklist the token
    return {"message": "Successfully logged out"}
