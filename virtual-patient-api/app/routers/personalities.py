from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.personality import Personality, PersonalityCreate, PersonalityUpdate, PersonalityListResponse
from app.controllers.personality_controller import PersonalityController

router = APIRouter(
    prefix="/personalities", 
    tags=["personalities"],
    responses={404: {"description": "Personality not found"}},
)

@router.post("", response_model=Personality, status_code=status.HTTP_201_CREATED)
async def create_personality(
    personality_data: PersonalityCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new personality.
    
    - **name**: Name of the personality (required)
    - **namespace_key**: Unique namespace key for the personality (required)
    - **description**: Description of the personality (optional)
    - **name_translations**: Translations for the name field (optional)

    Returns the created personality.
    """
    controller = PersonalityController(db)
    
    try:
        personality = controller.create_personality(personality_data)
        return personality
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("", response_model=List[PersonalityListResponse])
async def get_personalities(
    skip: int = Query(0, ge=0, description="Number of personalities to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of personalities to return"),
    search: Optional[str] = Query(None, description="Search term for name or description"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all personalities with optional search and pagination.
    Returns only id and name in the user's preferred language.
    
    - **skip**: Number of personalities to skip (for pagination)
    - **limit**: Maximum number of personalities to return
    - **search**: Search term to filter by name or description
    
    Returns a list of personalities with id and name only.
    """
    controller = PersonalityController(db)
    preferred_language = current_user.preferred_language or "en"
    
    if search:
        personalities = controller.search_personalities_simplified(
            search, preferred_language=preferred_language, skip=skip, limit=limit
        )
    else:
        personalities = controller.get_all_personalities_simplified(
            preferred_language=preferred_language, skip=skip, limit=limit
        )
    
    return personalities

@router.get("/{personality_id}", response_model=PersonalityListResponse)
async def get_personality(
    personality_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get personality by ID.
    Returns only id and name in the user's preferred language.
    
    - **personality_id**: Unique identifier for the personality
    
    Returns the personality with id and name only.
    """
    controller = PersonalityController(db)
    preferred_language = current_user.preferred_language or "en"
    
    personality = controller.get_personality_simplified(personality_id, preferred_language=preferred_language)
    if not personality:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Personality not found"
        )
    
    return personality

@router.get("/namespace/{namespace_key}", response_model=PersonalityListResponse)
async def get_personality_by_namespace_key(
    namespace_key: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get personality by namespace key.
    Returns only id and name in the user's preferred language.
    
    - **namespace_key**: Unique namespace key for the personality
    
    Returns the personality with id and name only.
    """
    controller = PersonalityController(db)
    preferred_language = current_user.preferred_language or "en"
    
    personality = controller.get_personality_by_namespace_key_simplified(namespace_key, preferred_language=preferred_language)
    if not personality:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Personality not found"
        )
    
    return personality

@router.post("/{personality_id}", response_model=Personality)
async def update_personality(
    personality_id: int,
    personality_data: PersonalityUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update personality.
    
    - **personality_id**: Unique identifier for the personality
    - **personality_data**: Fields to update
    
    Returns the updated personality.
    """
    controller = PersonalityController(db)
    
    try:
        personality = controller.update_personality(personality_id, personality_data)
        if not personality:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Personality not found"
            )
        return personality
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/{personality_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personality(
    personality_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete personality.
    
    - **personality_id**: Unique identifier for the personality
    
    Deletes the personality permanently.
    """
    controller = PersonalityController(db)
    
    success = controller.delete_personality(personality_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Personality not found"
        )
