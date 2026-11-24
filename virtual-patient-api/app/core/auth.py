from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User, UserInDB, TokenData, UserDB, UserRole
from app.core.database import get_db
from app.core.config import settings
from app.core.web_session import read_session_token

# Security configuration
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user(db: Session, user_id: int) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.id == user_id).first()


def authenticate_user(db: Session, email: str, password: str) -> Optional[UserDB]:
    """Authenticate by email without modifying the supplied password."""
    identifier = email.strip().lower()
    if not identifier:
        return None
    matches = db.query(UserDB).filter(
        func.lower(UserDB.email) == identifier,
    ).limit(2).all()
    if len(matches) != 1:
        return None
    user = matches[0]
    if user.disabled or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "identity_version": 2})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_from_token(token: str, db: Session) -> Optional[User]:
    """
    Get current user from a raw token string (used for media access authentication).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if payload.get("identity_version") != 2 or payload.get("type") == "refresh" or not isinstance(subject, str) or not subject.isdigit():
            return None
        token_data = TokenData(user_id=int(subject))
    except JWTError:
        return None
    user = get_user(db, user_id=token_data.user_id)
    if user is None:
        return None
    return user

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = credentials.credentials if credentials is not None else read_session_token(request)
    user = get_current_user_from_token(token, db) if token else None
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
