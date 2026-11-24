from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from app.core.media_cookie import set_media_cookie, clear_media_cookie
from app.core.web_session import clear_web_session, is_web_session_request, set_web_session
from sqlalchemy.orm import Session
from pydantic import ConfigDict, EmailStr
from jose import JWTError, jwt
from app.models.user import User, Token, WebSession, EmailIdentity
from app.core.auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.core.database import get_db
from app.core.captcha import require_captcha

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

class TokenRequest(EmailIdentity):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str

@router.post("/token", response_model=Token | WebSession, dependencies=[Depends(require_captcha)])
def login_for_access_token(
    token_request: TokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    web_session = is_web_session_request(request)
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
    if web_session:
        expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        set_web_session(request, response, access_token, expires_in)
        return {"expires_in": expires_in}
    set_media_cookie(response, access_token)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }

@router.post("/logout")
async def logout(request: Request, response: Response, current_user: User = Depends(get_current_active_user)):
    clear_web_session(request, response)
    clear_media_cookie(response)
    # In a real application, you might want to blacklist the token
    return {"message": "Successfully logged out"}
