"""
Translator Agent with Personality Support
Translates messages to specific languages and adds personality traits to responses
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
from pydantic import BaseModel
from .schemas.progress_summary import ProgressSummarySchema

if TYPE_CHECKING:
    from .schemas.progress_summary import ProgressSummarySchema

from .prompts.translator import (
    BASIC_TRANSLATE_PROMPT,
    STRUCTURED_TRANSLATE_PROMPT
)
from .prompts.personalities import build_personality_prompt
from .schemas.clinical_case import ClinicalCaseTranslatableFields

load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_NAME_MINI = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_MINI")
AZURE_OPENAI_API_VERSION_MINI = os.getenv("AZURE_OPENAI_API_VERSION_MINI")

# Initialize LLM with Azure OpenAI
llm = init_chat_model(
    "azure_openai:gpt-4o-mini",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME_MINI,
    api_version=AZURE_OPENAI_API_VERSION_MINI,
    temperature=0.2
)

llm_personality = init_chat_model(
    "azure_openai:gpt-4.1",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
    api_version=AZURE_OPENAI_API_VERSION,
    temperature=1
)


class TranslatorAgent:
    """
    Agent that translates messages to specific languages and adds personality traits
    """
    
    def __init__(self):
        self.llm = llm
        self.llm_personality = llm_personality
        print("Translator Agent initialized with Azure OpenAI")
    
    async def basic_translate(
        self, 
        message: str, 
        target_language: str
    ) -> str:
        """
        Basic translation from language A to language B (ASYNC)
        
        Args:
            message: Original message to translate
            target_language: Target language (e.g., "Spanish", "French", "English")
            
        Returns:
            Translated message
        """
        try:
            # Format the prompt
            formatted_prompt = BASIC_TRANSLATE_PROMPT.format(
                target_language=target_language,
                message=message
            )
            
            # Create message and get response ASYNC
            messages = [HumanMessage(content=formatted_prompt)]
            response = await self.llm.ainvoke(messages)
            
            return response.content.strip()
            
        except Exception as e:
            print(f"Error in basic_translate: {e}")
            return f"Translation error: {str(e)}"
    
    async def translate_patient_with_personality(
        self, 
        patient_message: str, 
        target_language: str, 
        personality_key: str,
        patient_gender: Optional[str] = None,
        patient_name: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Translate a PATIENT response with personality adaptation (ASYNC)
        
        Args:
            patient_message: Original patient message to translate
            target_language: Target language (e.g., "Spanish", "French", "English")
            personality_key: Personality key (e.g., "elderly_forgetful", "know_it_all")
            patient_gender: Patient gender for proper gender agreement (e.g., "male", "female")
            patient_name: Patient name for personalization (e.g., "Maria", "John")
            conversation_history: List of previous messages for context
            
        Returns:
            Translated and personalized patient response
        """
        try:
            # Format conversation history for the prompt
            # Note: conversation_history contains only previous patient responses
            history_text = "No previous patient responses."
            if conversation_history and len(conversation_history) > 0:
                history_lines = []
                for i, msg in enumerate(conversation_history, 1):
                    content = msg.get("content", "")
                    history_lines.append(f"Previous Response {i}: {content}")
                history_text = "\n".join(history_lines)
            
            # Build the personality prompt using the new function
            formatted_prompt = build_personality_prompt(
                personality_key=personality_key,
                language=target_language,
                conversation_history=history_text,
                message=patient_message,
                patient_name=patient_name,
                patient_gender=patient_gender
            )
            
            # Create message and get response ASYNC
            messages = [HumanMessage(content=formatted_prompt)]
            response = await self.llm_personality.ainvoke(messages)
            
            return response.content.strip()
            
        except Exception as e:
            print(f"Error in translate_patient_with_personality: {e}")
            return f"Translation error: {str(e)}"
    
    
    async def translate_progress_summary(
        self, 
        progress_summary: ProgressSummarySchema, 
        target_language: str
    ) -> ProgressSummarySchema:
        """
        Translate ProgressSummarySchema while preserving structure (ASYNC)
        
        Args:
            progress_summary: ProgressSummarySchema instance to translate
            target_language: Target language (e.g., "Spanish", "French", "English")
            
        Returns:
            Translated ProgressSummarySchema with same structure
        """
        try:
            # Convert to dictionary
            data_dict = progress_summary.model_dump()
            
            # Convert to JSON string for translation
            json_string = json.dumps(data_dict, ensure_ascii=False, indent=2)
            
            # Format the prompt
            formatted_prompt = STRUCTURED_TRANSLATE_PROMPT.format(
                target_language=target_language,
                structured_data=json_string
            )
            
            # Create message
            messages = [HumanMessage(content=formatted_prompt)]
            
            # Use structured output with ProgressSummarySchema
            print(f"🔄 Creating structured model for {target_language}...")
            model_with_structure = self.llm.with_structured_output(ProgressSummarySchema)
            print(f"✅ Structured model created")
            
            # Get structured response with timeout handling
            print(f"🔄 Invoking LLM for translation...")
            try:
                # Add timeout to prevent hanging
                translated_summary = await asyncio.wait_for(
                    model_with_structure.ainvoke(messages), 
                    timeout=35.0
                )
                print(f"✅ LLM translation completed")
                return translated_summary
            except asyncio.TimeoutError:
                print(f"⚠️ LLM translation timed out after 35 seconds")
                print(f"🔄 Falling back to original summary...")
                return progress_summary
            except Exception as llm_error:
                print(f"⚠️ LLM translation failed: {llm_error}")
                print(f"🔄 Falling back to original summary...")
                return progress_summary
                
        except Exception as e:
            print(f"Error in translate_progress_summary: {e}")
            # Return original data if translation fails
            return progress_summary
    
    async def translate_clinical_case_fields(
        self,
        clinical_case_fields: ClinicalCaseTranslatableFields,
        target_language: str
    ) -> ClinicalCaseTranslatableFields:
        """
        Translate ClinicalCaseTranslatableFields while preserving structure (ASYNC)
        
        Args:
            clinical_case_fields: ClinicalCaseTranslatableFields instance to translate
            target_language: Target language (e.g., "Spanish", "English")
            
        Returns:
            Translated ClinicalCaseTranslatableFields with same structure
        """
        try:
            # Convert to dictionary
            data_dict = clinical_case_fields.model_dump(exclude_none=True)
            
            # Convert to JSON string for translation
            json_string = json.dumps(data_dict, ensure_ascii=False, indent=2)
            
            # Format the prompt - use STRUCTURED_TRANSLATE_PROMPT for clinical cases
            formatted_prompt = STRUCTURED_TRANSLATE_PROMPT.format(
                target_language=target_language,
                structured_data=json_string
            )
            
            # Create message
            messages = [HumanMessage(content=formatted_prompt)]
            
            # Use structured output with ClinicalCaseTranslatableFields
            print(f"🔄 Creating structured model for clinical case translation to {target_language}...")
            model_with_structure = self.llm.with_structured_output(ClinicalCaseTranslatableFields)
            print(f"✅ Structured model created")
            
            # Get structured response with timeout handling
            print(f"🔄 Invoking LLM for clinical case translation...")
            try:
                # Add timeout to prevent hanging
                translated_fields = await asyncio.wait_for(
                    model_with_structure.ainvoke(messages),
                    timeout=35.0
                )
                print(f"✅ LLM translation completed")
                return translated_fields
            except asyncio.TimeoutError:
                print(f"⚠️ LLM translation timed out after 35 seconds")
                print(f"🔄 Falling back to original fields...")
                return clinical_case_fields
            except Exception as llm_error:
                print(f"⚠️ LLM translation failed: {llm_error}")
                print(f"🔄 Falling back to original fields...")
                return clinical_case_fields
                
        except Exception as e:
            print(f"Error in translate_clinical_case_fields: {e}")
            # Return original data if translation fails
            return clinical_case_fields
    
    def get_supported_languages(self) -> List[str]:
        """
        Get a list of supported languages
        
        Returns:
            List of language names
        """
        return ["Spanish", "English", "French", "German", "Italian"]
