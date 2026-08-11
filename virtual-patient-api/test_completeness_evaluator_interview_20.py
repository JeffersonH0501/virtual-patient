#!/usr/bin/env python3
"""
Test script for Completeness Evaluator using Medical Interview ID 20 (Spanish)
This test retrieves actual data from the database and tests the completeness evaluation in Spanish,
displaying all prompts used during the evaluation process.
"""

import asyncio
import sys
import os
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.core.database import SessionLocal
from app.agents.evaluation_agent import EvaluationAgent
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.agents.schemas.evaluation import EvaluationResult

load_dotenv()

class CompletenessEvaluatorTest:
    """Test class for completeness evaluator using real interview data"""
    
    def __init__(self):
        self.db: Optional[Session] = None
        self.interview_controller: Optional[MedicalInterviewController] = None
        self.evaluation_agent: Optional[EvaluationAgent] = None
        self.interview_id = 20
    
    def setup_database(self):
        """Setup database connection and controllers"""
        print("🔧 Setting up database connection...")
        try:
            self.db = SessionLocal()
            self.interview_controller = MedicalInterviewController(self.db)
            print("✅ Database connection established")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def cleanup_database(self):
        """Cleanup database connection"""
        if self.db:
            self.db.close()
            print("🔒 Database connection closed")
    
    def get_interview_data(self) -> Optional[Dict[str, Any]]:
        """Get interview data for ID 20"""
        print(f"📋 Retrieving interview data for ID {self.interview_id}...")
        
        try:
            # Check if interview exists
            interview = self.interview_controller.get_interview(self.interview_id)
            if not interview:
                print(f"❌ Interview with ID {self.interview_id} not found")
                return None
            
            print(f"✅ Found interview: {interview.id}")
            print(f"   Status: {interview.status}")
            print(f"   Clinical Case ID: {interview.clinical_case_id}")
            print(f"   Start Time: {interview.start_time}")
            
            # Get complete interview data for evaluation
            evaluation_data = self.interview_controller.get_interview_evaluation_data(self.interview_id)
            
            if not evaluation_data:
                print(f"❌ Could not retrieve evaluation data for interview {self.interview_id}")
                return None
            
            # Check what data we have
            has_messages = bool(evaluation_data.get("messages"))
            has_progress_summary = bool(evaluation_data.get("progress_summary"))
            has_clinical_case = bool(evaluation_data.get("clinical_case"))
            
            print(f"📊 Data availability:")
            print(f"   Messages: {'✅' if has_messages else '❌'}")
            print(f"   Progress Summary: {'✅' if has_progress_summary else '❌'}")
            print(f"   Clinical Case: {'✅' if has_clinical_case else '❌'}")
            
            if has_messages:
                print(f"   Message count: {len(evaluation_data['messages'])}")
            
            return evaluation_data
            
        except Exception as e:
            print(f"❌ Error retrieving interview data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def display_interview_details(self, evaluation_data: Dict[str, Any]):
        """Display detailed information about the interview"""
        print(f"\n📋 Interview Details for ID {self.interview_id}")
        print("=" * 60)
    
        # Display message information
        messages = evaluation_data.get("messages", [])
        if messages:
            print(f"\n💬 Conversation Information:")
            print(f"   Total Messages: {len(messages)}")
            
            # Show first few messages
            for i, message in enumerate(messages[:5]):
                role = message.get('role', 'unknown') if isinstance(message, dict) else getattr(message, 'sender_type', 'unknown')
                content = message.get('content', 'N/A') if isinstance(message, dict) else getattr(message, 'content', 'N/A')
                print(f"   Message {i+1} ({role}): {content[:100]}...")
            
            if len(messages) > 5:
                print(f"   ... and {len(messages) - 5} more messages")
    
    async def test_completeness_evaluation(self, evaluation_data: Dict[str, Any]):
        """Test the completeness evaluation in Spanish"""
        print(f"\n🔍 Testing Completeness Evaluation in Spanish")
        print("=" * 60)
        
        try:
            # Initialize evaluation agent with Spanish
            self.evaluation_agent = EvaluationAgent(target_language="Spanish")
            print("✅ Evaluation agent initialized with Spanish language")
            
            # Get required data
            clinical_case = evaluation_data.get("clinical_case")
            progress_summary = evaluation_data.get("progress_summary")
            
            if not clinical_case:
                print("❌ No clinical case data available for evaluation")
                return False
            
            if not progress_summary:
                print("❌ No progress summary data available for evaluation")
                return False
            
            print("✅ Required data available for completeness evaluation")
            
            # Display the prompt that will be used
            print(f"\n📝 Completeness Evaluation Prompt (Spanish):")
            print("-" * 50)
            
            # Run completeness evaluation
            print(f"\n🎯 Running completeness evaluation in Spanish...")
            result = await self.evaluation_agent.evaluate_completeness(
                clinical_case=clinical_case,
                progress_summary=progress_summary
            )
            
            # Display results
            print(f"\n📊 Completeness Evaluation Results (Spanish):")
            print(f"   Aspect: {result.aspect}")
            print(f"   Score: {result.score}/10")
            print(f"   Feedback: {result.feedback}")
            
            # Validate result
            assert isinstance(result, EvaluationResult), "Result should be an EvaluationResult instance"
            assert result.aspect == "completeness", "Aspect should be 'completeness'"
            assert isinstance(result.score, int), "Score should be an integer"
            assert 1 <= result.score <= 10, "Score should be between 1 and 10"
            assert isinstance(result.feedback, str), "Feedback should be a string"
            assert len(result.feedback) > 0, "Feedback should not be empty"
            
            print("✅ Completeness evaluation test passed!")
            return True
            
        except Exception as e:
            print(f"❌ Completeness evaluation test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_comprehensive_test(self):
        """Run comprehensive test suite in Spanish"""
        print("🚀 Starting Completeness Evaluator Test for Interview ID 20 (Spanish)")
        print("=" * 80)
        
        success = True
        
        try:
            # Setup
            if not self.setup_database():
                return False
            
            # Get interview data
            evaluation_data = self.get_interview_data()
            if not evaluation_data:
                print("❌ Could not retrieve interview data")
                return False
            
            # Display interview details
            self.display_interview_details(evaluation_data)
            
            # Test completeness evaluation
            if not await self.test_completeness_evaluation(evaluation_data):
                success = False
            
            if success:
                print(f"\n🎉 All tests completed successfully!")
            else:
                print(f"\n⚠️ Some tests failed, but evaluation completed")
            
            return success
            
        except Exception as e:
            print(f"\n❌ Test suite failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            self.cleanup_database()

async def main():
    """Main test function"""
    test = CompletenessEvaluatorTest()
    success = await test.run_comprehensive_test()
    
    if success:
        print("\n✅ Test completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
