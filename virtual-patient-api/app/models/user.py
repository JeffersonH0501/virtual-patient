from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy import Boolean, Column, String, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

# Enum for user roles
class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    STUDENT = "student"
    SUPERUSER = "superuser"

# SQLAlchemy Model
class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    disabled = Column(Boolean, default=False)
    preferred_language = Column(String, default="en")
    role = Column(Enum(UserRole, name='user_role', values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=UserRole.STUDENT)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    medical_interviews = relationship("MedicalInterviewDB", back_populates="user")
    organization = relationship("OrganizationDB")

# Pydantic Models
class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    preferred_language: Optional[str] = "en"
    role: Optional[UserRole] = UserRole.STUDENT
    organization_id: Optional[int] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    preferred_language: Optional[str] = None
    role: Optional[UserRole] = None
    organization_id: Optional[int] = None

class User(UserBase):
    id: int
    
    class Config:
        from_attributes = True

class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: Optional[int] = None

class TokenData(BaseModel):
    username: Optional[str] = None
