"""
Evaluation Agent for Virtual Patient System
Evaluates doctor's performance in medical interviews
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .schemas import EvaluationResult
from .prompts.evaluation_prompts import get_evaluation_prompts
from .helpers.formatting_helpers import (
    format_demographics,
    format_simple_field,
    format_dict_field,
    format_list_field
)
from app.models.clinical_case import ClinicalCase
from app.models.medical_interview.progress_summary import ProgressSummary

load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

# Initialize LLM
llm = init_chat_model(
    "azure_openai:gpt-4.1",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
    api_version=AZURE_OPENAI_API_VERSION,
    temperature=0.7
)

class EvaluationAgent:
    """
    Agent that evaluates doctor's performance in medical interviews
    """
    
    def __init__(self, target_language: str = "English", patient_gender: Optional[str] = None):
        self.llm = llm
        self.target_language = target_language
        self.patient_gender = patient_gender
        self.evaluation_prompts = get_evaluation_prompts(target_language, patient_gender)
        self.structured_model = self.llm.with_structured_output(EvaluationResult)
    


    async def evaluate_conversation(
        self, 
        conversation_messages: List[Dict[str, Any]] = None,
        aspect: str = "show_interest",
        conversation_text: Optional[str] = None
    ) -> EvaluationResult:
        """
        Evaluate the doctor's performance in a medical interview
        
        Args:
            conversation_messages: List of conversation messages (optional if conversation_text provided)
            aspect: Aspect to evaluate
            conversation_text: Pre-formatted conversation text (optional, for optimization)
            
        Returns:
            EvaluationResult with score and feedback
        """
        if aspect not in self.evaluation_prompts:
            raise ValueError(f"Unknown evaluation aspect: {aspect}. Available aspects: {list(self.evaluation_prompts.keys())}")
        
        # Format conversation for evaluation if not provided
        if conversation_text is None:
            if conversation_messages is None:
                raise ValueError("Either conversation_messages or conversation_text must be provided")
            conversation_text = self._format_conversation(conversation_messages)
        
        # Create evaluation prompt
        evaluation_prompt = self.evaluation_prompts[aspect]
        
        # Create messages for LLM
        messages = [
            SystemMessage(content=evaluation_prompt),
            HumanMessage(content=f"Please evaluate the following medical interview conversation for {aspect}:\n\n{conversation_text}")
        ]
        
        # Get evaluation from LLM using structured output
        try:
            # Use cached structured model
            result = await self.structured_model.ainvoke(messages)
            
            # Ensure the aspect is set correctly
            if result.aspect != aspect:
                result.aspect = aspect
            
            return result
            
        except Exception as e:
            print(f"Error in evaluation for {aspect}: {e}")
            # Return a default evaluation result
            return EvaluationResult(
                aspect=aspect,
                score=5,
                feedback=f"Evaluation failed due to technical error: {str(e)}"
            )
    
    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Format conversation messages for evaluation"""
        formatted_conversation = []
        
        for message in messages:
            if isinstance(message, dict):
                role = message.get("role", "unknown")
                content = message.get("content", "")
            else:
                role = getattr(message, "type", "unknown")
                content = getattr(message, "content", "")
            
            if role == "user" or "human" in role.lower():
                formatted_conversation.append(f"DOCTOR: {content}")
            elif role == "assistant" or "ai" in role.lower():
                formatted_conversation.append(f"PATIENT: {content}")
            else:
                formatted_conversation.append(f"{role.title()}: {content}")

        return "\n\n".join(formatted_conversation)
    
    async def evaluate_completeness(
        self,
        clinical_case: ClinicalCase,
        progress_summary: ProgressSummary,
        hypotheses: Optional[List[Any]] = None,
        conversation_text: Optional[str] = None
    ) -> EvaluationResult:
        """
        Evaluate the completeness of a doctor's interview by comparing clinical case with progress summary.
        Also evaluates hypotheses against the clinical case if provided.
        Combines both evaluations with weighted average.
        
        Args:
            clinical_case: Clinical case information (ClinicalCase object)
            progress_summary: Progress summary from the interview (ProgressSummary object)
            hypotheses: Optional list of user hypotheses to evaluate against clinical case
            conversation_text: Pre-formatted conversation text (optional, for phase 2 verification)
            
        Returns:
            EvaluationResult with combined score and feedback
        """
        # Run both evaluations in parallel
        tasks = []
        
        # Original completeness evaluation (progress summary vs clinical case)
        # Pass conversation text for phase 2 verification
        tasks.append(self._evaluate_progress_summary_completeness(clinical_case, progress_summary, conversation_text=conversation_text))
        
        # Hypothesis evaluation (if hypotheses provided)
        if hypotheses and len(hypotheses) > 0:
            tasks.append(self._evaluate_hypothesis_completeness(clinical_case, hypotheses))
        
        # Run evaluations in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        progress_result = None
        hypothesis_result = None
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Error in completeness evaluation {i}: {result}")
                continue
            
            if i == 0:
                progress_result = result
            elif i == 1:
                hypothesis_result = result
        
        # If only one result (no hypotheses), return it directly
        if hypothesis_result is None:
            return progress_result if progress_result else EvaluationResult(
                aspect="completeness",
                score=5,
                feedback="Completeness evaluation failed"
            )
        
        # Combine both results with weighted average (70% progress, 30% hypothesis)
        # Calculate weighted average score
        print(f"Progress result score: {progress_result.score}")
        print(f"Hypothesis result score: {hypothesis_result.score}")
        combined_score = (progress_result.score * 0.7) + (hypothesis_result.score * 0.3)
        
        # Concatenate feedbacks with a space
        combined_feedback = f"{progress_result.feedback} \n\n {hypothesis_result.feedback}"
        
        return EvaluationResult(
            aspect="completeness",
            score=round(combined_score, 1),
            feedback=combined_feedback
        )
    
    async def _evaluate_progress_summary_completeness(
        self,
        clinical_case: ClinicalCase,
        progress_summary: ProgressSummary,
        conversation_text: Optional[str] = None
    ) -> EvaluationResult:
        """
        Two-phase completeness evaluation:
        Phase 1: Compare progress summary vs clinical case
        Phase 2: Verify the result against the full conversation
        """
        if "completeness" not in self.evaluation_prompts:
            raise ValueError("Completeness evaluation prompt not found")
        
        # Format clinical case and progress summary for evaluation
        clinical_case_text = self._format_clinical_case(clinical_case)
        progress_summary_text = self._format_progress_summary(progress_summary)
        
        # ===== PHASE 1: Compare summary vs clinical case =====
        print("📊 PHASE 1: Evaluating completeness (summary vs clinical case)...")
        evaluation_prompt = self.evaluation_prompts["completeness"]
        
        # Create messages for LLM
        messages = [
            SystemMessage(content=evaluation_prompt),
            HumanMessage(content=f"Evaluate the completeness of this medical interview:\n\n{clinical_case_text}\n\n{progress_summary_text}")
        ]
        
        # Get initial evaluation from LLM using structured output
        try:
            phase1_result = await self.structured_model.ainvoke(messages)
            phase1_result.aspect = "completeness"
            print(f"✅ PHASE 1 Result: Score={phase1_result.score}/10")
            print(f"   Feedback: {phase1_result.feedback[:100]}...")
        except Exception as e:
            print(f"❌ Error in phase 1 evaluation: {e}")
            return EvaluationResult(
                aspect="completeness",
                score=5,
                feedback=f"Progress summary completeness evaluation failed due to technical error: {str(e)}"
            )
        
        # ===== PHASE 2: Verify against full conversation =====
        if conversation_text:
            print("📊 PHASE 2: Verifying evaluation against full conversation...")
            if "completeness_verification" not in self.evaluation_prompts:
                print("⚠️  Completeness verification prompt not found, skipping phase 2")
                return phase1_result
            
            # Create verification prompt
            verification_prompt = self.evaluation_prompts["completeness_verification"]
            
            # Format initial evaluation for verification (format is described in the prompt)
            initial_evaluation_text = f"""[INITIAL EVALUATION]
Score: {phase1_result.score}/10
Feedback: {phase1_result.feedback}"""
            
            # Create messages for phase 2
            verification_messages = [
                SystemMessage(content=verification_prompt),
                HumanMessage(content=f"""{initial_evaluation_text}

[FULL CONVERSATION]
{conversation_text}""")
            ]
            
            # Get verification result from LLM
            try:
                phase2_result = await self.structured_model.ainvoke(verification_messages)
                phase2_result.aspect = "completeness"
                print(f"✅ PHASE 2 Result: Score={phase2_result.score}/10 (adjusted from {phase1_result.score}/10)")
                print(f"   Feedback: {phase2_result.feedback[:100]}...")
                return phase2_result
            except Exception as e:
                print(f"⚠️  Error in phase 2 verification: {e}, returning phase 1 result")
                return phase1_result
        else:
            print("⚠️  No conversation text provided, skipping phase 2 verification")
            return phase1_result
    
    async def _evaluate_hypothesis_completeness(
        self,
        clinical_case: ClinicalCase,
        hypotheses: List[Any]
    ) -> EvaluationResult:
        """Evaluate hypotheses against clinical case"""
        if "hypothesis_completeness" not in self.evaluation_prompts:
            raise ValueError("Hypothesis completeness evaluation prompt not found")
        
        # Format clinical case and hypotheses for evaluation
        clinical_case_text = self._format_clinical_case(clinical_case)
        hypotheses_text = self._format_hypotheses(hypotheses)
        print(f"Clinical case text (for hypotheses): {clinical_case_text}")
        print(f"Hypotheses text: {hypotheses_text}")
        
        # Create evaluation prompt
        evaluation_prompt = self.evaluation_prompts["hypothesis_completeness"]
        
        # Create messages for LLM
        messages = [
            SystemMessage(content=evaluation_prompt),
            HumanMessage(content=f"Evaluate the hypotheses against the clinical case:\n\n{clinical_case_text}\n\n{hypotheses_text}")
        ]
        
        # Get evaluation from LLM using structured output
        try:
            # Use cached structured model
            result = await self.structured_model.ainvoke(messages)
            
            # Ensure the aspect is set correctly
            result.aspect = "completeness"
            
            return result
            
        except Exception as e:
            print(f"Error in hypothesis completeness evaluation: {e}")
            # Return a default evaluation result
            return EvaluationResult(
                aspect="completeness",
                score=5,
                feedback=f"Hypothesis completeness evaluation failed due to technical error: {str(e)}"
            )
    
    def _format_hypotheses(self, hypotheses: List[Any]) -> str:
        """Format hypotheses for evaluation"""
        formatted = "[USER HYPOTHESES]\n"
        
        for i, hypothesis in enumerate(hypotheses, start=1):
            if hasattr(hypothesis, 'hypothesis_text'):
                # It's a Pydantic model or object
                hypothesis_text = hypothesis.hypothesis_text
            elif isinstance(hypothesis, dict):
                # It's a dictionary
                hypothesis_text = hypothesis.get('hypothesis_text', hypothesis.get('text', str(hypothesis)))
            else:
                # Fallback: convert to string
                hypothesis_text = str(hypothesis)
            
            formatted += f"Hypothesis {i}: {hypothesis_text}\n"
        
        return formatted.strip()
    
    def _format_clinical_case(self, clinical_case: ClinicalCase) -> str:
        """Format clinical case for evaluation"""
        formatted = "[CLINICAL CASE]\n"
        
        # Map clinical case fields to readable format
        field_mapping = {
            "age": "Age",
            "weight_in_kg": "Weight",
            "description": "Description",
            "chief_complaint": "Chief Complaint",
            "present_illness": "Present Illness",
            "personal_medical_history": "Personal Medical History",
            "surgical_history": "Surgical History",
            "family_history": "Family History",
            "medications": "Medications",
            "habits": "Habits",
            "allergies": "Allergies",
            "socioeconomic_status": "Socioeconomic Status",
            "patient_context": "Patient Context",
            "concerns": "Concerns"
        }
        
        for field, label in field_mapping.items():
            if hasattr(clinical_case, field):
                value = getattr(clinical_case, field)
                if value is not None:
                    if field == "age":
                        formatted += f"{label}: {value} years old\n"
                    elif field == "weight_in_kg":
                        formatted += f"{label}: {value} kg\n"
                    else:
                        formatted += f"{label}: {value}\n"
        
        return formatted.strip()
    
    def _format_progress_summary(self, progress_summary: ProgressSummary) -> str:
        """Format progress summary for evaluation"""
        formatted = "[PROGRESS SUMMARY]\n"
        
        # Convert ProgressSummary to dict for the helper functions
        if hasattr(progress_summary, 'dict'):
            # It's a Pydantic model
            summary_dict = progress_summary.dict()
        elif hasattr(progress_summary, '__dict__'):
            # It's an object with attributes
            summary_dict = progress_summary.__dict__
        elif isinstance(progress_summary, dict):
            # It's already a dictionary
            summary_dict = progress_summary
        else:
            # Fallback: try to convert to string
            return f"[PROGRESS SUMMARY]\n{str(progress_summary)}"
        
        formatted += format_demographics(summary_dict)
        formatted += format_list_field(summary_dict, "current_symptoms", "Current Symptoms")
        formatted += format_list_field(summary_dict, "allergies", "Allergies", default_text="None")
        formatted += format_dict_field(summary_dict, "diet_information", "Diet Information")
        formatted += format_list_field(summary_dict, "current_illnesses", "Current Illnesses")
        formatted += format_simple_field(summary_dict, "summary_text", "Summary")
        
        return formatted.strip()
    

    
    async def evaluate_multiple_aspects(
        self, 
        conversation_messages: List[Dict[str, Any]], 
        aspects: List[str] = None
    ) -> List[EvaluationResult]:
        """
        Evaluate multiple aspects of the doctor's performance in parallel
        
        Args:
            conversation_messages: List of conversation messages
            aspects: List of aspects to evaluate
            
        Returns:
            List of EvaluationResult objects
        """
        if aspects is None:
            aspects = ["show_interest"]
        
        # Filter out completeness as it requires different inputs
        conversation_aspects = [a for a in aspects if a != "completeness"]
        
        if not conversation_aspects:
            return []
        
        # Format conversation once and reuse for all evaluations
        conversation_text = self._format_conversation(conversation_messages)
        
        # Create tasks for parallel evaluation
        tasks = [
            self.evaluate_conversation(
                conversation_text=conversation_text,
                aspect=aspect
            )
            for aspect in conversation_aspects
        ]
        
        # Run all evaluations in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out any exceptions and keep only successful results
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Error evaluating aspect '{conversation_aspects[i]}': {result}")
                # Add a fallback result for failed evaluations
                valid_results.append(EvaluationResult(
                    aspect=conversation_aspects[i],
                    score=5,
                    feedback=f"Evaluation failed: {str(result)}"
                ))
            else:
                valid_results.append(result)
        
        return valid_results
    
    async def evaluate_all_aspects(
        self,
        conversation_messages: List[Dict[str, Any]],
        clinical_case: Optional[ClinicalCase] = None,
        progress_summary: Optional[ProgressSummary] = None,
        hypotheses: Optional[List[Any]] = None,
        aspects: List[str] = None
    ) -> List[EvaluationResult]:
        """
        Evaluate all aspects in parallel (including completeness if data is provided)
        
        Args:
            conversation_messages: List of conversation messages
            clinical_case: Clinical case for completeness evaluation (optional)
            progress_summary: Progress summary for completeness evaluation (optional)
            hypotheses: Optional list of user hypotheses for hypothesis completeness evaluation
            aspects: List of aspects to evaluate (default: ["show_interest", "show_empathy", "speak_clearly"])
            
        Returns:
            List of EvaluationResult objects
        """
        if aspects is None:
            aspects = ["general_communication", "show_interest", "show_empathy", "speak_clearly", "open_communication"]
        
        tasks = []
        
        # Separate conversation aspects from completeness
        conversation_aspects = [a for a in aspects if a != "completeness"]
        include_completeness = "completeness" in aspects
        
        # Add conversation evaluations (will run in parallel internally)
        if conversation_aspects:
            tasks.append(self.evaluate_multiple_aspects(conversation_messages, conversation_aspects))
        
        # Add completeness evaluation if data is provided (includes hypothesis evaluation if hypotheses provided)
        if include_completeness and clinical_case and progress_summary:
            # Format conversation text once for completeness evaluation
            conversation_text = self._format_conversation(conversation_messages)
            tasks.append(self.evaluate_completeness(clinical_case, progress_summary, hypotheses, conversation_text))
        
        # Run all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten and collect all results
        all_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in evaluation: {result}")
            elif isinstance(result, list):
                all_results.extend(result)
            else:
                all_results.append(result)
        
        return all_results
