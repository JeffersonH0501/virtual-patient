from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.models.organization import Organization, OrganizationCreate, OrganizationUpdate, OrganizationDB
from app.models.user import User
from app.core.auth import get_current_active_user
from app.core.database import get_db

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"]
)

@router.post("", response_model=Organization, status_code=status.HTTP_201_CREATED)
async def create_organization(
    organization: OrganizationCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Check if organization ID already exists
    db_organization = db.query(OrganizationDB).filter(OrganizationDB.id == organization.id).first()
    if db_organization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID already registered"
        )
    
    # Create new organization
    db_organization = OrganizationDB(**organization.dict())
    db.add(db_organization)
    db.commit()
    db.refresh(db_organization)
    
    return db_organization

@router.get("", response_model=List[Organization])
async def get_organizations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    organizations = db.query(OrganizationDB).filter(OrganizationDB.active == True).offset(skip).limit(limit).all()
    return organizations

@router.get("/{organization_id}", response_model=Organization)
async def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    organization = db.query(OrganizationDB).filter(
        OrganizationDB.id == organization_id,
        OrganizationDB.active == True
    ).first()
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return organization

@router.post("/{organization_id}", response_model=Organization)
async def update_organization(
    organization_id: int,
    organization_update: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    db_organization = db.query(OrganizationDB).filter(OrganizationDB.id == organization_id).first()
    if db_organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Update only provided fields
    update_data = organization_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_organization, field, value)
    
    db.commit()
    db.refresh(db_organization)
    return db_organization

@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    db_organization = db.query(OrganizationDB).filter(OrganizationDB.id == organization_id).first()
    if db_organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Soft delete - set active to False
    db_organization.active = False
    db.commit()
    
    return {"message": "Organization deleted successfully"} 