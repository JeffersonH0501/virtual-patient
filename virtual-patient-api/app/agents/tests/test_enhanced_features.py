"""
Test script for enhanced virtual patient agent features
Demonstrates context awareness, feedback system, and enhanced memory
"""

import asyncio
import uuid
from app.agents.virtual_patient_agent import VirtualPatientAgent
from app.core.database import SQLALCHEMY_DATABASE_URL
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.embeddings import init_embeddings
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize embeddings
embeddings = init_embeddings(
    "azure_openai:text-embedding-3-small",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_EMBEDDING_DEPLOYMENT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

async def test_enhanced_features():
    """Test the enhanced virtual patient agent features"""
    
    print("🧪 Testing Enhanced Virtual Patient Agent Features")
    print("=" * 60)
    
    with (
        PostgresStore.from_conn_string(SQLALCHEMY_DATABASE_URL,
                                      index={
                                          "dims": 1536,
                                          "embed": embeddings,
                                      }) as store,
        PostgresSaver.from_conn_string(SQLALCHEMY_DATABASE_URL) as checkpointer,
    ):
        # Create agent with enhanced features
        user_id = str(uuid.uuid4())[:8]
        agent = VirtualPatientAgent(store=store, checkpointer=checkpointer, user_id=user_id)
        
        session_id = f"test-session-{uuid.uuid4()}"
        clinical_case_id = "enhanced-test-case"
        
        print(f"📋 User ID: {user_id}")
        print(f"🧵 Session ID: {session_id}")
        print(f"🏥 Clinical Case: {clinical_case_id}")
        print("-" * 60)
        
        # Test 1: Basic conversation with context tracking
        print("\n🔍 Test 1: Context-Aware Conversation")
        print("-" * 40)
        
        test_questions = [
            "Hello, how are you feeling today?",
            "Do you have any pain or discomfort?",
            "When did this pain start?",
            "Can you describe the intensity of the pain?",
            "Have you been taking any medication for the pain?"
        ]
        
        for i, question in enumerate(test_questions, 1):
            print(f"\n📝 Question {i}: {question}")
            
            result = await agent.process_medical_interview_message(
                messages=[question],
                clinical_case_id=clinical_case_id,
                thread_id=session_id
            )
            
            patient_response = result["messages"][-1].content
            print(f"👤 Patient: {patient_response}")
            
            # Show context summary
            memories = agent.search_patient_memories("patient information")
            if memories and memories != "No previous memories available":
                print(f"🧠 Memory Context: {memories[:200]}...")
        
        # Test 2: Feedback collection
        print("\n\n🔍 Test 2: Feedback System")
        print("-" * 40)
        
        # Simulate doctor feedback
        feedback_result = agent.collect_doctor_feedback(
            session_id=session_id,
            question="Do you have any pain or discomfort?",
            patient_response="Yes, I have headaches that are pretty persistent.",
            doctor_feedback="The patient's response was good but could be more specific about the pain intensity and duration. Should mention pain scale (1-10) and how long symptoms have been present.",
            feedback_type="improvement"
        )
        
        print(f"✅ Feedback processed: {feedback_result}")
        
        # Test 3: Consistency check
        print("\n\n🔍 Test 3: Consistency Check")
        print("-" * 40)
        
        # Ask a follow-up question to test consistency
        follow_up_result = await agent.process_medical_interview_message(
            messages=["You mentioned headaches earlier. Are they still the same intensity?"],
            clinical_case_id=clinical_case_id,
            thread_id=session_id
        )
        
        follow_up_response = follow_up_result["messages"][-1].content
        print(f"📝 Follow-up Question: You mentioned headaches earlier. Are they still the same intensity?")
        print(f"👤 Patient: {follow_up_response}")
        
        # Test 4: Enhanced memory retrieval
        print("\n\n🔍 Test 4: Enhanced Memory Retrieval")
        print("-" * 40)
        
        # Search for specific types of memories
        semantic_memories = agent.enhanced_memory.semantic.search_facts("headache", fact_type="symptoms")
        
        print(f"📊 Semantic Memories (symptoms): {len(semantic_memories)} found")
        
        # Test 5: Procedural memory
        print("\n\n🔍 Test 5: Procedural Memory")
        print("-" * 40)
        
        # Test different question types
        question_types = ["pain_assessment", "medication_inquiry", "family_history", "lifestyle_questions"]
        
        for question_type in question_types:
            guidance = agent.enhanced_memory.procedural.get_response_guidance(question_type)
            if guidance:
                print(f"📋 {question_type}: {guidance.get('pattern', 'No pattern found')}")
        
        print("\n✅ Enhanced Features Test Completed!")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_enhanced_features()) 