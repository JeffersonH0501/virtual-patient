"""
Summary Controller
Handles summary workflow processing separately from the main interview workflow
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from app.agents.summary_workflow import create_summary_workflow
from app.core.azure_openai import EMBEDDING_DIMENSIONS, create_embeddings
from app.core.database import SQLALCHEMY_DATABASE_URL
from app.models.clinical_case import ClinicalCaseDB

# Initialize Azure OpenAI v1 embeddings.
embeddings = create_embeddings()


class SummaryController:
    """
    Controller for managing summary workflow processing
    """
    
    def __init__(self):
        pass
    
    async def process_summary(
        self,
        interview_id: int,
        messages: List[Dict[str, str]],
        clinical_case: ClinicalCaseDB,
        user_preferred_language: str = "English"
    ) -> Dict[str, Any]:
        """
        Process summary generation and translation
        
        Args:
            interview_id: The interview ID
            messages: List of message dictionaries with role and content
            clinical_case: The clinical case object
            user_preferred_language: User's preferred language for responses
        
        Returns:
            Dictionary containing the summary result
        """
        print(f"🔍 DEBUG SummaryController: user_preferred_language = '{user_preferred_language}'")
        
        # Use context managers for proper resource management
        with (
            PostgresStore.from_conn_string(
                SQLALCHEMY_DATABASE_URL,
                index={
                    "dims": EMBEDDING_DIMENSIONS,
                    "embed": embeddings,
                }
            ) as store,
            PostgresSaver.from_conn_string(SQLALCHEMY_DATABASE_URL) as checkpointer,
        ):
            try:
                # Create summary workflow with user's preferred language
                workflow = create_summary_workflow(
                    store=store, 
                    checkpointer=checkpointer, 
                    interview_id=str(interview_id),
                    current_language=user_preferred_language
                )
                
                print(f"🔍 DEBUG SummaryController: Created workflow with language '{user_preferred_language}'")
                
                result = await workflow.process_summary(
                    messages=messages,
                    clinical_case=clinical_case
                )
                return result
                
            except Exception as e:
                print(f"Error processing summary through workflow: {e}")
                raise
