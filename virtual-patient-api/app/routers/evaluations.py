"""
Evaluations Router
Handles evaluation-related endpoints
"""

from fastapi import APIRouter, Depends
from app.agents.prompts.evaluation_aspects import get_all_aspects
from app.core.auth import get_current_active_user
from app.models.user import UserDB

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

@router.get("/aspects")
async def get_evaluation_aspects(current_user: UserDB = Depends(get_current_active_user)):
    """
    Get all evaluation aspects organized by category
    Uses the current user's preferred language
    """
    # Get user's preferred language, default to English
    user_language = getattr(current_user, 'preferred_language', 'en')
    
    aspects = get_all_aspects(user_language)
    
    return {
        "aspects": aspects
    }

