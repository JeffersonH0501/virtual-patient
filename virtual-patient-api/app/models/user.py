from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator
from typing import Annotated, Literal, Optional
from sqlalchemy import Boolean, Column, String, Integer, Enum, ForeignKey, Index, func
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
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    __table_args__ = (Index("uq_users_email_normalized", func.lower(email), unique=True),)
    hashed_password = Column(String)
    disabled = Column(Boolean, default=False)
    preferred_language = Column(String, default="en")
    role = Column(Enum(UserRole, name='user_role', values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=UserRole.STUDENT)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    medical_interviews = relationship("MedicalInterviewDB", back_populates="user")
    organization = relationship("OrganizationDB")

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# The registration form collects a single "Name" value, stored in the ``name``
# column.


class EmailIdentity(BaseModel):
    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


# Pydantic Models
class UserBase(EmailIdentity):
    email: EmailStr
    name: str
    disabled: Optional[bool] = None
    preferred_language: Optional[str] = "en"
    role: Optional[UserRole] = UserRole.STUDENT
    organization_id: Optional[int] = None

class UserCreate(EmailIdentity):
    """Fields accepted by the public registration endpoint."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: Name
    preferred_language: Optional[str] = "en"
    role: Literal[UserRole.TEACHER, UserRole.STUDENT] = UserRole.STUDENT
    password: str

class UserUpdate(EmailIdentity):
    """Non-privileged fields users may update on their own profile."""

    model_config = ConfigDict(extra="forbid")

    email: Optional[EmailStr] = None
    name: Optional[Name] = None
    preferred_language: Optional[str] = None

    @field_validator("email", "name", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("Identity fields cannot be null")
        return value


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
    user_id: int
