"""
Test script for Evaluation Agent
Tests the evaluation of doctor's performance in medical interviews
"""

import asyncio
import uuid
from typing import List, Dict, Any
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.schemas.evaluation import EvaluationResult
import os
from dotenv import load_dotenv

load_dotenv()

def test_evaluation_agent():
    """Test the evaluation agent functionality"""
    print("Testing Evaluation Agent")
    print("=" * 60)
    
    # Create evaluation agent
    evaluation_agent = EvaluationAgent()
    
    async def run_all_tests():
        try:
            print(f"\n🎭 Evaluation Agent Test Session Started")
            print(f"📋 Agent Type: Evaluation Agent")
            print(f"🎯 Evaluation Aspects: show_interest, show_empathy, speak_clearly, completeness")
            print("-" * 60)
            
            # Run all aspect tests
            await test_agent_initialization(evaluation_agent)
            #await test_show_interest_aspect(evaluation_agent)
            #await test_show_empathy_aspect(evaluation_agent)
            #await test_speak_clearly_aspect(evaluation_agent)
            await test_completeness_aspect(evaluation_agent)
            #await test_multiple_aspects(evaluation_agent)
            #await test_error_handling(evaluation_agent)
            
            print(f"\n🎉 All evaluation agent tests completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_all_tests())


async def test_agent_initialization(evaluation_agent):
    """Test agent initialization and basic setup"""
    print("\n🔍 Test 1: Agent Initialization")
    print("-" * 40)
    assert evaluation_agent is not None
    assert hasattr(evaluation_agent, 'llm')
    assert hasattr(evaluation_agent, 'evaluation_prompts')
    assert 'show_interest' in evaluation_agent.evaluation_prompts
    assert 'show_empathy' in evaluation_agent.evaluation_prompts
    assert 'speak_clearly' in evaluation_agent.evaluation_prompts
    assert 'completeness' in evaluation_agent.evaluation_prompts
    print("✅ Agent initialization test passed")


async def test_show_interest_aspect(evaluation_agent):
    """Test show_interest aspect evaluation"""
    print("\n🔍 Test 2-5: Show Interest Aspect")
    print("-" * 40)
    
    conversations = get_test_conversations()
    
    # Test conversation formatting
    print("Testing conversation formatting...")
    formatted = evaluation_agent._format_conversation(conversations["good_conversation"])
    assert "Doctor: Good morning! How are you feeling today?" in formatted
    assert "Patient: Hello doctor. I've been having these terrible headaches" in formatted
    print("✅ Conversation formatting test passed")
    
    # Test good conversation
    print("Testing good conversation evaluation (Show Interest)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["good_conversation"], 
        aspect="show_interest"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_interest"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Good conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test poor conversation
    print("Testing poor conversation evaluation (Show Interest)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["poor_conversation"], 
        aspect="show_interest"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_interest"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Poor conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test mixed conversation
    print("Testing mixed conversation evaluation (Show Interest)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["mixed_conversation"], 
        aspect="show_interest"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_interest"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Mixed conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")


async def test_show_empathy_aspect(evaluation_agent):
    """Test show_empathy aspect evaluation"""
    print("\n🔍 Test 6-7: Show Empathy Aspect")
    print("-" * 40)
    
    conversations = get_test_conversations()
    
    # Test empathetic conversation
    print("Testing empathetic conversation evaluation (Show Empathy)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["empathetic_conversation"], 
        aspect="show_empathy"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_empathy"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Empathetic conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test non-empathetic conversation
    print("Testing non-empathetic conversation evaluation (Show Empathy)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["non_empathetic_conversation"], 
        aspect="show_empathy"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_empathy"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Non-empathetic conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")


async def test_speak_clearly_aspect(evaluation_agent):
    """Test speak_clearly aspect evaluation"""
    print("\n🔍 Test 8-9: Speak Clearly Aspect")
    print("-" * 40)
    
    conversations = get_test_conversations()
    
    # Test clear communication
    print("Testing clear communication evaluation (Speak Clearly)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["clear_communication_conversation"], 
        aspect="speak_clearly"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "speak_clearly"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Clear communication evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test unclear communication
    print("Testing unclear communication evaluation (Speak Clearly)...")
    result = await evaluation_agent.evaluate_conversation(
        conversations["unclear_communication_conversation"], 
        aspect="speak_clearly"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "speak_clearly"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Unclear communication evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")


async def test_completeness_aspect(evaluation_agent):
    """Test completeness aspect evaluation"""
    print("\n🔍 Test 10-14: Completeness Aspect")
    print("-" * 40)
    
    clinical_cases = get_test_clinical_cases()
    progress_summaries = get_test_progress_summaries()
    
    # Test good coverage
    print("Testing good coverage evaluation (Completeness)...")
    result = await evaluation_agent.evaluate_completeness(
        clinical_cases["diabetes_case"], 
        progress_summaries["good_coverage"]
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "completeness"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Good coverage evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test poor coverage
    print("Testing poor coverage evaluation (Completeness)...")
    result = await evaluation_agent.evaluate_completeness(
        clinical_cases["diabetes_case"], 
        progress_summaries["poor_coverage"]
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "completeness"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Poor coverage evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test mixed coverage
    print("Testing mixed coverage evaluation (Completeness)...")
    result = await evaluation_agent.evaluate_completeness(
        clinical_cases["diabetes_case"], 
        progress_summaries["mixed_coverage"]
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "completeness"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Mixed coverage evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test complex case
    print("Testing complex case evaluation (Completeness)...")
    result = await evaluation_agent.evaluate_completeness(
        clinical_cases["complex_case"], 
        progress_summaries["complex_summary"]
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "completeness"
    assert isinstance(result.score, int)
    assert 1 <= result.score <= 10
    print(f"✅ Complex case evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test empty inputs
    print("Testing empty inputs evaluation (Completeness)...")
    try:
        result = await evaluation_agent.evaluate_completeness({}, {})
        assert isinstance(result, EvaluationResult)
        assert result.aspect == "completeness"
        print(f"✅ Empty inputs evaluation completed: Score {result.score}/10")
        print(f"   Feedback: {result.feedback}")
    except Exception as e:
        print(f"✅ Empty inputs error handled correctly: {e}")


async def test_multiple_aspects(evaluation_agent):
    """Test multiple aspects evaluation"""
    print("\n🔍 Test 15: Multiple Aspects")
    print("-" * 40)
    
    conversations = get_test_conversations()
    
    # Test multiple aspects
    print("Testing multiple aspects evaluation...")
    results = await evaluation_agent.evaluate_multiple_aspects(
        conversations["good_conversation"],
        aspects=["show_interest", "show_empathy", "speak_clearly"]
    )
    
    assert isinstance(results, list)
    assert len(results) == 3
    assert all(isinstance(result, EvaluationResult) for result in results)
    aspects_evaluated = [result.aspect for result in results]
    assert "show_interest" in aspects_evaluated
    assert "show_empathy" in aspects_evaluated
    assert "speak_clearly" in aspects_evaluated
    
    print(f"✅ Multiple aspects evaluation completed:")
    for result in results:
        print(f"   {result.aspect}: {result.score}/10")
        print(f"   Feedback: {result.feedback}")


async def test_error_handling(evaluation_agent):
    """Test error handling"""
    print("\n🔍 Test 16: Error Handling")
    print("-" * 40)
    
    conversations = get_test_conversations()
    
    # Test invalid aspect
    print("Testing invalid aspect handling...")
    try:
        await evaluation_agent.evaluate_conversation(
            conversations["good_conversation"],
            aspect="invalid_aspect"
        )
        print("❌ Expected error was not raised")
    except ValueError as e:
        print(f"✅ Invalid aspect error handled correctly: {e}")
    
    # Test empty conversation
    print("Testing empty conversation handling...")
    empty_conversation = []
    result = await evaluation_agent.evaluate_conversation(
        empty_conversation,
        aspect="show_interest"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_interest"
    print(f"✅ Empty conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")
    
    # Test single message conversation
    print("Testing single message conversation...")
    single_message = [{"role": "user", "content": "Hello, how are you?"}]
    result = await evaluation_agent.evaluate_conversation(
        single_message,
        aspect="show_interest"
    )
    assert isinstance(result, EvaluationResult)
    assert result.aspect == "show_interest"
    print(f"✅ Single message conversation evaluation completed: Score {result.score}/10")
    print(f"   Feedback: {result.feedback}")


def get_test_conversations():
    """Get test conversation scenarios"""
    return {
        "good_conversation": [
            {"role": "user", "content": "Good morning! How are you feeling today?"},
            {"role": "assistant", "content": "Hello doctor. I've been having these terrible headaches for the past week."},
            {"role": "user", "content": "I'm sorry to hear that. Headaches can be really uncomfortable. Can you tell me more about when they started and what they feel like?"},
            {"role": "assistant", "content": "They started about a week ago, and they're mostly in the front of my head. They get worse in the evening."},
            {"role": "user", "content": "Thank you for sharing that with me. It sounds quite distressing. Have you noticed anything that makes them better or worse?"},
            {"role": "assistant", "content": "They seem to get worse when I'm stressed, and sometimes they're better in the morning."},
            {"role": "user", "content": "I understand this must be affecting your daily life. Let's work together to figure out what's causing this and how we can help you feel better."}
        ],
        
        "poor_conversation": [
            {"role": "user", "content": "Next. What's wrong?"},
            {"role": "assistant", "content": "I have stomach pain."},
            {"role": "user", "content": "Describe it."},
            {"role": "assistant", "content": "It hurts a lot, especially after I eat."},
            {"role": "user", "content": "Hmmm... that's bad. How long?"},
            {"role": "assistant", "content": "About three days."},
            {"role": "user", "content": "Fine. I'll order tests."}
        ],
        
        "mixed_conversation": [
            {"role": "user", "content": "Hello. What brings you in today?"},
            {"role": "assistant", "content": "I've been feeling very tired lately."},
            {"role": "user", "content": "Alright, let's go through your symptoms. Any other issues?"},
            {"role": "assistant", "content": "I also feel dizzy sometimes, especially when I stand up quickly."},
            {"role": "user", "content": "Hmmm, sorry, I'll note that. Any medications you're taking?"},
            {"role": "assistant", "content": "Just some vitamins."},
            {"role": "user", "content": "Good. Let me check your blood pressure."}
        ],
        
        "empathetic_conversation": [
            {"role": "user", "content": "Good morning. I can see you're looking quite worried. Please take your time and tell me what's been on your mind."},
            {"role": "assistant", "content": "I'm really scared, doctor. I've been having these chest pains and I'm afraid it might be something serious."},
            {"role": "user", "content": "I understand how frightening that must be for you. Chest pain can be very concerning, and it's completely normal to feel anxious about it. Let's work together to figure out what's going on."},
            {"role": "assistant", "content": "Thank you for understanding. I've been losing sleep over this."},
            {"role": "user", "content": "That's completely understandable. Let me ask you some questions to help us understand what's happening, and I want you to know that we're going to take this very seriously."}
        ],
        
        "non_empathetic_conversation": [
            {"role": "user", "content": "What's the problem?"},
            {"role": "assistant", "content": "I'm really scared about these chest pains I've been having."},
            {"role": "user", "content": "Just describe the symptoms. We don't have time for emotions."},
            {"role": "assistant", "content": "But I'm really worried about what it might be."},
            {"role": "user", "content": "Focus on the facts. When did the pain start?"}
        ],
        
        "clear_communication_conversation": [
            {"role": "user", "content": "You mentioned you have chest pain. Let me explain what I mean by that - it's any discomfort in the area around your heart. Can you tell me more about what it feels like?"},
            {"role": "assistant", "content": "It's like a pressure, mostly when I walk."},
            {"role": "user", "content": "That's helpful. What this could mean is that your heart isn't getting enough oxygen when you're active. Does that make sense to you?"},
            {"role": "assistant", "content": "Yes, I think so."},
            {"role": "user", "content": "Good. My recommendation is to run some tests to confirm what's happening. We'll start with a simple blood test and an ECG, which is a test that shows your heart's electrical activity. Does that sound clear?"}
        ],
        
        "unclear_communication_conversation": [
            {"role": "user", "content": "You have angina pectoris. We need to do a coronary angiography."},
            {"role": "assistant", "content": "What does that mean?"},
            {"role": "user", "content": "It's a procedure to check your coronary arteries."},
            {"role": "assistant", "content": "I don't understand. Is it dangerous?"},
            {"role": "user", "content": "It's a standard procedure. Just sign the consent form."}
        ]
    }


def get_test_clinical_cases():
    """Get test clinical cases for completeness evaluation"""
    return {
        "diabetes_case": {
            "id": 1,
            "title": "Type 2 Diabetes Management",
            "description": "70-year-old male with diabetes management",
            "name": "John Smith",
            "age": 70,
            "gender": "Male",
            "weight_in_kg": 75.0,
            "physical_requirements": "Regular exercise recommended",
            "socioeconomic_status": "High socioeconomic status, retired",
            "general_attitude": "Collaborative and disciplined",
            "patient_context": "Lives with wife, two children, one granddaughter, Catholic",
            "chief_complaint": "Diabetes management follow-up",
            "present_illness": "Type 2 diabetes for 13 years, well-controlled",
            "personal_medical_history": "Hypertension, controlled with medication",
            "surgical_history": "Appendectomy 20 years ago",
            "family_history": "Father had diabetes, mother had hypertension",
            "medications": "Metformin 500mg twice daily, Lisinopril 10mg daily",
            "habits": "Non-smoker, occasional alcohol, regular exercise",
            "allergies": "None known",
            "concerns": "Worried about long-term complications"
        },
        
        "complex_case": {
            "id": 2,
            "title": "Hypertension and Chest Pain",
            "description": "45-year-old female with chest pain and hypertension",
            "name": "Maria Garcia",
            "age": 45,
            "gender": "Female",
            "weight_in_kg": 68.0,
            "physical_requirements": "Cardiac stress test recommended",
            "socioeconomic_status": "Middle class, works as teacher",
            "general_attitude": "Anxious and concerned",
            "patient_context": "Single mother, two teenage children, works full-time",
            "chief_complaint": "Chest pain for 3 days",
            "present_illness": "Intermittent chest pain, worse with stress, associated with shortness of breath",
            "personal_medical_history": "Hypertension diagnosed 2 years ago, anxiety disorder",
            "surgical_history": "C-section 15 years ago",
            "family_history": "Father died of heart attack at 50, mother has diabetes",
            "medications": "Lisinopril 20mg daily, Alprazolam 0.5mg as needed",
            "habits": "Smokes 10 cigarettes per day, sedentary lifestyle",
            "allergies": "Penicillin (rash)",
            "concerns": "Fear of heart disease, financial stress"
        }
    }


def get_test_progress_summaries():
    """Get test progress summaries for completeness evaluation"""
    return {
        "good_coverage": {
            "age": 70,
            "gender": "Male",
            "weight_in_kg": 75.0,
            "current_symptoms": [
                {
                    "symptom": "Diabetes management",
                    "duration": "13 years",
                    "status": "Well-controlled"
                }
            ],
            "allergies": [],
            "diet_information": {
                "diet_type": "Diabetic diet",
                "follows_nutritionist": True,
                "meals": "Regular 3 meals per day"
            },
            "current_illnesses": [
                {
                    "condition": "Type 2 Diabetes",
                    "duration": "13 years",
                    "treatment": "Metformin 500mg twice daily",
                    "status": "Well-controlled"
                }
            ],
            "summary_text": "Patient is a 70-year-old male with well-controlled type 2 diabetes for 13 years. He follows a diabetic diet and takes Metformin regularly. He is adherent to medication and follows healthy habits."
        },
        
        "poor_coverage": {
            "age": 70,
            "current_symptoms": [
                {
                    "symptom": "Diabetes",
                    "duration": "13 years"
                }
            ],
            "allergies": [],
            "diet_information": {},
            "current_illnesses": [],
            "summary_text": "Patient has diabetes."
        },
        
        "mixed_coverage": {
            "age": 70,
            "gender": "Male",
            "current_symptoms": [
                {
                    "symptom": "Diabetes management",
                    "duration": "13 years"
                }
            ],
            "allergies": [],
            "diet_information": {
                "diet_type": "Diabetic diet"
            },
            "current_illnesses": [
                {
                    "condition": "Type 2 Diabetes",
                    "duration": "13 years"
                }
            ],
            "summary_text": "Patient is a 70-year-old male with diabetes for 13 years. Follows diabetic diet."
        },
        
        "complex_summary": {
            "age": 45,
            "gender": "Female",
            "current_symptoms": [
                {
                    "symptom": "Chest pain",
                    "duration": "3 days",
                    "severity": "Moderate",
                    "triggers": "Stress"
                }
            ],
            "allergies": [
                {
                    "allergen": "Penicillin",
                    "reaction": "Rash"
                }
            ],
            "diet_information": {},
            "current_illnesses": [
                {
                    "condition": "Hypertension",
                    "duration": "2 years",
                    "treatment": "Lisinopril 20mg daily"
                }
            ],
            "summary_text": "45-year-old female with chest pain for 3 days, history of hypertension. Allergic to penicillin."
        }
    }
    


if __name__ == "__main__":
    test_evaluation_agent()
