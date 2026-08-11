from pydantic import BaseModel
from typing import Optional
from sqlalchemy import Boolean, Column, String, DateTime, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

# SQLAlchemy Model
class OrganizationDB(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship to clinical cases
    clinical_cases = relationship("ClinicalCaseDB", back_populates="organization")

# Pydantic Models
class OrganizationBase(BaseModel):
    name: str
    description: Optional[str] = None
    active: Optional[bool] = True

class OrganizationCreate(OrganizationBase):
    id: int

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

class Organization(OrganizationBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True 