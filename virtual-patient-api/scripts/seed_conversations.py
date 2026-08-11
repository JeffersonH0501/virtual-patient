#!/usr/bin/env python3
"""
Seed mock conversations in the database for testing purposes.
This script creates realistic medical interview conversations with messages,
hypotheses, and session notes.
"""

import os
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Import the models
from app.models.medical_interview import (
    MedicalInterviewDB, InterviewMessageDB, UserHypothesisDB, 
    MedicalSessionNoteDB, ProgressSummaryDB, InterviewEvaluationDB
)
from app.models.medical_interview.enums import InterviewStatus, SenderType, NoteType
from app.models.user import UserDB, UserRole
from app.models.clinical_case import ClinicalCaseDB
from app.models.personality import PersonalityDB

# Load environment variables
load_dotenv()

def get_database_url():
    """Get database URL from environment variables"""
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB', 'virtual_patient')
    db_user = os.getenv('POSTGRES_USER', 'postgres')
    db_password = os.getenv('POSTGRES_PASSWORD', 'postgres')
    
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Enhanced conversation templates with much more variety
CONVERSATION_TEMPLATES = {
    "diabetes": {
        "patient_responses": [
            "Hello doctor, I've been feeling very tired lately and I'm always thirsty.",
            "I've been drinking a lot of water, maybe 8-10 glasses a day, but I'm still thirsty.",
            "Yes, I've been going to the bathroom more frequently, especially at night.",
            "I've lost about 10 pounds in the last month without trying.",
            "I do have a family history of diabetes. My mother has type 2 diabetes.",
            "I haven't been exercising much lately due to work stress.",
            "My diet has been mostly fast food and processed meals.",
            "I've been feeling dizzy sometimes, especially when I stand up quickly.",
            "I have been experiencing some blurry vision recently.",
            "I'm worried about my health. Could this be diabetes?",
            "I've been getting up 3-4 times a night to use the bathroom.",
            "I'm always hungry but I'm still losing weight somehow.",
            "My feet have been tingling and numb sometimes.",
            "I've been getting frequent yeast infections.",
            "My cuts and bruises seem to take longer to heal."
        ],
        "user_questions": [
            "Hello, I'm Dr. Smith. Can you tell me what brings you in today?",
            "How long have you been experiencing these symptoms?",
            "How much water would you say you're drinking daily?",
            "Have you noticed any changes in your urination patterns?",
            "Have you experienced any weight changes recently?",
            "Is there a family history of diabetes or other metabolic conditions?",
            "What's your current exercise routine like?",
            "Can you describe your typical daily diet?",
            "Have you experienced any dizziness or lightheadedness?",
            "Any changes in your vision recently?",
            "How many times do you urinate during the day?",
            "Have you noticed any changes in your appetite?",
            "Any numbness or tingling in your hands or feet?",
            "Any recent infections or slow-healing wounds?",
            "Based on your symptoms, I'd like to order some blood tests to check your blood sugar levels."
        ],
        "hypotheses": [
            "Type 2 Diabetes Mellitus - Classic triad of polydipsia, polyuria, and weight loss",
            "Hyperglycemia - Elevated blood glucose levels causing osmotic diuresis",
            "Diabetic ketoacidosis - Severe complication requiring immediate treatment",
            "Pre-diabetes - Early stage of glucose intolerance",
            "Type 1 Diabetes - Autoimmune destruction of pancreatic beta cells"
        ],
        "session_notes": [
            "Patient presents with classic diabetes symptoms: polydipsia, polyuria, weight loss",
            "Strong family history of type 2 diabetes increases risk",
            "Lifestyle factors include poor diet and lack of exercise",
            "Patient appears concerned and motivated to address health issues",
            "Consider HbA1c, fasting glucose, and oral glucose tolerance test"
        ]
    },
    "copd": {
        "patient_responses": [
            "Good morning doctor. I've been having trouble breathing lately.",
            "I've been a smoker for about 30 years, about a pack a day.",
            "The shortness of breath is worse in the morning and when I walk up stairs.",
            "I have a persistent cough that's been getting worse over the past year.",
            "Yes, I cough up phlegm, especially in the mornings. It's usually clear or white.",
            "I've had to stop playing golf because I get too winded.",
            "I wake up at night sometimes feeling like I can't catch my breath.",
            "I've been using an inhaler that my previous doctor gave me, but it doesn't help much.",
            "I know I should quit smoking, but it's been very difficult.",
            "I'm worried this might be something serious."
        ],
        "user_questions": [
            "Hello, I'm Dr. Johnson. What seems to be the problem today?",
            "How long have you been experiencing breathing difficulties?",
            "Do you smoke? If so, for how long and how much?",
            "When do you notice the shortness of breath most?",
            "Do you have a cough? If so, is it productive?",
            "How has this affected your daily activities?",
            "Do you experience any breathing problems at night?",
            "Are you currently using any medications or inhalers?",
            "Have you tried to quit smoking before?",
            "I'd like to order a chest X-ray and pulmonary function tests to better understand what's happening."
        ],
        "hypotheses": [
            "Chronic Obstructive Pulmonary Disease (COPD) - Long-term smoking history with progressive symptoms",
            "Emphysema - Destruction of alveoli causing air trapping and dyspnea",
            "Chronic bronchitis - Inflammation of airways with productive cough",
            "Asthma - Reversible airway obstruction, though less likely given smoking history"
        ],
        "session_notes": [
            "30-year smoking history with progressive dyspnea and productive cough",
            "Symptoms consistent with COPD - morning cough, exercise intolerance",
            "Patient shows motivation to quit smoking",
            "Pulmonary function tests and chest imaging needed for definitive diagnosis"
        ]
    },
    "hypertension": {
        "patient_responses": [
            "Hi doctor, I came in for my routine checkup, but I've been having headaches.",
            "The headaches are usually in the morning and feel like pressure in my head.",
            "I've been feeling more tired than usual lately.",
            "I do have a family history of high blood pressure. My father had it.",
            "I've been under a lot of stress at work recently.",
            "I don't exercise regularly, maybe once a week if I'm lucky.",
            "My diet includes a lot of processed foods and I add salt to most meals.",
            "I drink about 2-3 cups of coffee a day.",
            "I've been having some chest discomfort, but it's not severe.",
            "I'm concerned about my health. My father had a heart attack at 55."
        ],
        "user_questions": [
            "Hello, I'm Dr. Williams. What brings you in today?",
            "Can you describe the headaches you've been experiencing?",
            "Have you noticed any other symptoms recently?",
            "Is there a family history of cardiovascular disease?",
            "How would you describe your stress levels lately?",
            "What's your current exercise routine?",
            "Can you tell me about your typical diet?",
            "How much caffeine do you consume daily?",
            "Have you experienced any chest pain or discomfort?",
            "I'd like to check your blood pressure and order some lab work."
        ],
        "hypotheses": [
            "Essential Hypertension - Elevated blood pressure with family history and lifestyle risk factors",
            "Secondary Hypertension - Rule out underlying causes like kidney disease or endocrine disorders",
            "Hypertensive Crisis - Severe elevation requiring immediate intervention",
            "White Coat Hypertension - Anxiety-related elevation in clinical setting"
        ],
        "session_notes": [
            "Patient presents with headaches and family history of hypertension",
            "Multiple cardiovascular risk factors: stress, poor diet, lack of exercise",
            "Strong family history of cardiovascular disease",
            "Blood pressure monitoring and lifestyle counseling needed"
        ]
    },
    "asthma": {
        "patient_responses": [
            "Doctor, I've been wheezing a lot lately, especially at night.",
            "I've had asthma since I was a child, but it's been getting worse recently.",
            "I've been using my inhaler more often, sometimes 3-4 times a day.",
            "The wheezing is worse when I exercise or when it's cold outside.",
            "I've been waking up at night coughing and having trouble breathing.",
            "I have allergies to pollen and dust, which seem to trigger it.",
            "I've been avoiding going outside because of my breathing problems.",
            "My chest feels tight and I can't take deep breaths.",
            "I've been missing work because of my breathing problems.",
            "I'm scared this might be getting worse. What can I do?"
        ],
        "user_questions": [
            "Hello, I'm Dr. Martinez. What brings you in today?",
            "Can you describe the breathing problems you've been having?",
            "How long have you had asthma?",
            "How often are you using your rescue inhaler?",
            "What seems to trigger your breathing problems?",
            "Are you experiencing any nighttime symptoms?",
            "Do you have any known allergies?",
            "How has this affected your daily activities?",
            "Are you currently taking any controller medications?",
            "Let's review your asthma action plan and adjust your treatment."
        ],
        "hypotheses": [
            "Asthma exacerbation - Worsening of chronic airway inflammation",
            "Allergic asthma - Triggered by environmental allergens",
            "Exercise-induced asthma - Bronchospasm during physical activity",
            "Nocturnal asthma - Nighttime worsening of symptoms"
        ],
        "session_notes": [
            "Patient with known asthma experiencing increased symptoms",
            "Frequent rescue inhaler use indicates poor control",
            "Allergic triggers identified - pollen and dust",
            "Consider step-up in controller therapy and allergy management"
        ]
    },
    "migraine": {
        "patient_responses": [
            "Doctor, I've been getting terrible headaches that last for hours.",
            "The pain is usually on one side of my head and it's throbbing.",
            "I get nauseous and sometimes vomit during these headaches.",
            "Bright lights and loud noises make it much worse.",
            "I have to lie down in a dark room when I get them.",
            "I've been getting them about twice a week for the past month.",
            "I notice I get them more often when I'm stressed at work.",
            "Sometimes I see flashing lights before the headache starts.",
            "I've been taking over-the-counter pain medication but it doesn't help much.",
            "These headaches are really affecting my work and personal life."
        ],
        "user_questions": [
            "Hello, I'm Dr. Chen. Can you tell me about these headaches?",
            "Can you describe the pain - is it throbbing, sharp, or dull?",
            "Do you experience any nausea or vomiting with the headaches?",
            "Are you sensitive to light or sound during the headaches?",
            "How long do the headaches typically last?",
            "How often are you getting these headaches?",
            "What seems to trigger them?",
            "Do you experience any visual changes before the headache?",
            "What medications have you tried for the pain?",
            "How are these headaches affecting your daily life?"
        ],
        "hypotheses": [
            "Migraine without aura - Severe unilateral headache with nausea and photophobia",
            "Migraine with aura - Visual disturbances preceding headache",
            "Tension-type headache - Bilateral pressure-like pain",
            "Cluster headache - Severe unilateral orbital pain"
        ],
        "session_notes": [
            "Patient presents with classic migraine symptoms",
            "Headaches significantly impacting quality of life",
            "Stress appears to be a trigger factor",
            "Consider migraine prophylaxis and lifestyle modifications"
        ]
    },
    "depression": {
        "patient_responses": [
            "Doctor, I've been feeling really down lately, like nothing matters.",
            "I can't sleep properly - either I can't fall asleep or I wake up too early.",
            "I've lost interest in things I used to enjoy, like reading and gardening.",
            "I feel tired all the time, even after a full night's sleep.",
            "I've been having trouble concentrating at work.",
            "My appetite has changed - sometimes I'm not hungry, other times I overeat.",
            "I feel guilty about things that aren't really my fault.",
            "I've been having thoughts that life isn't worth living.",
            "I've been isolating myself from friends and family.",
            "I just don't feel like myself anymore."
        ],
        "user_questions": [
            "Hello, I'm Dr. Thompson. How have you been feeling lately?",
            "Can you tell me more about what's been troubling you?",
            "How has your sleep been recently?",
            "Have you noticed any changes in your interests or activities?",
            "How has your energy level been?",
            "Are you having any trouble concentrating or making decisions?",
            "How has your appetite been?",
            "Have you been feeling guilty or worthless?",
            "Have you had any thoughts of hurting yourself?",
            "How has this been affecting your relationships with others?"
        ],
        "hypotheses": [
            "Major Depressive Disorder - Persistent low mood with multiple symptoms",
            "Dysthymia - Chronic mild depression lasting 2+ years",
            "Adjustment Disorder - Depression in response to life stressors",
            "Bipolar Depression - Depressive episode in bipolar disorder"
        ],
        "session_notes": [
            "Patient presents with classic depression symptoms",
            "Significant functional impairment reported",
            "Suicidal ideation requires immediate assessment",
            "Consider psychiatric referral and antidepressant therapy"
        ]
    },
    "anxiety": {
        "patient_responses": [
            "Doctor, I've been feeling really anxious and worried all the time.",
            "My heart races and I feel like I can't catch my breath.",
            "I'm constantly worried about things that might go wrong.",
            "I've been having trouble sleeping because my mind won't stop racing.",
            "I feel tense and on edge all day long.",
            "I've been avoiding social situations because I feel so nervous.",
            "I get dizzy and sweaty when I'm in crowded places.",
            "I've been having panic attacks where I feel like I'm dying.",
            "I can't stop thinking about worst-case scenarios.",
            "This anxiety is really taking over my life."
        ],
        "user_questions": [
            "Hello, I'm Dr. Rodriguez. What's been causing you anxiety?",
            "Can you describe what happens when you feel anxious?",
            "What physical symptoms do you experience?",
            "What kinds of things are you worried about?",
            "How has this been affecting your sleep?",
            "Are you avoiding any situations because of anxiety?",
            "Have you experienced any panic attacks?",
            "How long have you been feeling this way?",
            "What have you tried to manage your anxiety?",
            "How is this affecting your daily life and relationships?"
        ],
        "hypotheses": [
            "Generalized Anxiety Disorder - Excessive worry about multiple life areas",
            "Panic Disorder - Recurrent panic attacks with fear of future attacks",
            "Social Anxiety Disorder - Fear of social situations and judgment",
            "Agoraphobia - Fear of being in situations where escape might be difficult"
        ],
        "session_notes": [
            "Patient presents with significant anxiety symptoms",
            "Panic attacks and avoidance behaviors noted",
            "Significant functional impairment reported",
            "Consider cognitive behavioral therapy and medication options"
        ]
    },
    "heart_disease": {
        "patient_responses": [
            "Doctor, I've been having chest pain and shortness of breath.",
            "The pain feels like pressure in my chest, especially when I walk.",
            "I get tired easily and have to stop and rest frequently.",
            "I've been having some swelling in my ankles and feet.",
            "I feel like my heart is racing sometimes, even when I'm resting.",
            "I've been having some dizziness, especially when I stand up.",
            "I have a family history of heart disease - my father had a heart attack.",
            "I've been a smoker for 20 years, though I'm trying to quit.",
            "I don't exercise much and my diet isn't great.",
            "I'm worried this might be something serious with my heart."
        ],
        "user_questions": [
            "Hello, I'm Dr. Wilson. Can you describe the chest pain you've been having?",
            "When do you experience the chest pain?",
            "Can you describe the sensation - is it pressure, sharp, or burning?",
            "How has your breathing been?",
            "Have you noticed any swelling in your legs or feet?",
            "Have you experienced any palpitations or irregular heartbeat?",
            "Do you have a family history of heart disease?",
            "Do you smoke or have you smoked in the past?",
            "What's your current exercise routine?",
            "I'd like to order some tests to check your heart function."
        ],
        "hypotheses": [
            "Coronary Artery Disease - Chest pain due to reduced blood flow to heart",
            "Heart Failure - Reduced pumping ability causing fluid retention",
            "Arrhythmia - Irregular heart rhythm causing palpitations",
            "Angina - Chest pain due to temporary reduced blood flow"
        ],
        "session_notes": [
            "Patient presents with chest pain and cardiovascular risk factors",
            "Family history of heart disease increases risk",
            "Smoking history and sedentary lifestyle noted",
            "ECG, echocardiogram, and stress test recommended"
        ]
    },
    "thyroid": {
        "patient_responses": [
            "Doctor, I've been feeling really tired and sluggish lately.",
            "I've gained about 15 pounds in the last few months without changing my diet.",
            "I feel cold all the time, even when others are comfortable.",
            "My hair has been falling out more than usual.",
            "I've been feeling depressed and moody lately.",
            "My skin has been dry and I've been constipated.",
            "I've been having trouble concentrating and my memory seems worse.",
            "My voice has been hoarse and I feel like there's something in my throat.",
            "I've been feeling weak, especially in my muscles.",
            "I'm worried something is wrong with my thyroid."
        ],
        "user_questions": [
            "Hello, I'm Dr. Kim. What symptoms have you been experiencing?",
            "How has your energy level been?",
            "Have you noticed any weight changes recently?",
            "How has your body temperature been?",
            "Have you noticed any changes in your hair or skin?",
            "How has your mood been lately?",
            "Any changes in your bowel habits?",
            "Have you noticed any changes in your voice or throat?",
            "How has your muscle strength been?",
            "I'd like to check your thyroid function with some blood tests."
        ],
        "hypotheses": [
            "Hypothyroidism - Underactive thyroid causing metabolic slowdown",
            "Hashimoto's Thyroiditis - Autoimmune thyroid disease",
            "Thyroid Nodule - Benign or malignant growth in thyroid",
            "Goiter - Enlarged thyroid gland"
        ],
        "session_notes": [
            "Patient presents with classic hypothyroidism symptoms",
            "Weight gain, fatigue, and cold intolerance noted",
            "Thyroid function tests and thyroid ultrasound recommended",
            "Consider endocrinology referral if abnormal results"
        ]
    },
    "arthritis": {
        "patient_responses": [
            "Doctor, my joints have been really stiff and painful lately.",
            "The pain is worse in the morning and it takes a while to get moving.",
            "My hands are swollen and it's hard to make a fist.",
            "My knees and hips hurt when I walk or go up stairs.",
            "The pain gets better with movement but worse with rest.",
            "I've been having trouble sleeping because of the joint pain.",
            "I can't do simple tasks like opening jars or buttoning my shirt.",
            "The weather seems to affect my pain - it's worse on rainy days.",
            "I've been taking ibuprofen but it doesn't help much anymore.",
            "I'm worried I won't be able to work if this gets worse."
        ],
        "user_questions": [
            "Hello, I'm Dr. Patel. Can you tell me about your joint pain?",
            "Which joints are bothering you most?",
            "When is the pain worst - morning, evening, or all day?",
            "Have you noticed any swelling in your joints?",
            "How has this been affecting your daily activities?",
            "Does movement help or make the pain worse?",
            "How has this been affecting your sleep?",
            "What medications have you tried for the pain?",
            "Have you noticed any connection with weather changes?",
            "I'd like to examine your joints and order some tests."
        ],
        "hypotheses": [
            "Rheumatoid Arthritis - Autoimmune joint inflammation",
            "Osteoarthritis - Degenerative joint disease",
            "Psoriatic Arthritis - Joint inflammation associated with psoriasis",
            "Gout - Uric acid crystal deposition in joints"
        ],
        "session_notes": [
            "Patient presents with joint pain and stiffness",
            "Morning stiffness and swelling suggest inflammatory arthritis",
            "Functional impairment affecting daily activities",
            "Consider rheumatology referral and inflammatory markers"
        ]
    }
}

def create_mock_conversation(session, user_id: int, clinical_case_id: int, personality_id: int = None, case_type: str = "diabetes"):
    """Create a complete mock conversation with messages, hypotheses, and notes"""
    
    # Get the conversation template
    template = CONVERSATION_TEMPLATES.get(case_type, CONVERSATION_TEMPLATES["diabetes"])
    
    # Create the medical interview with more variety
    start_time = datetime.now() - timedelta(
        days=random.randint(1, 30), 
        hours=random.randint(0, 23), 
        minutes=random.randint(0, 59)
    )
    
    # More diverse patient names and genders
    patient_names = [
        "John Doe", "Jane Smith", "Robert Johnson", "Maria Garcia", "David Wilson",
        "Sarah Brown", "Michael Davis", "Lisa Anderson", "James Taylor", "Emily White",
        "Christopher Lee", "Jennifer Martinez", "Daniel Rodriguez", "Ashley Thompson", 
        "Matthew Garcia", "Jessica Wilson", "Ryan Moore", "Amanda Clark", "Kevin Lewis",
        "Stephanie Walker", "Brandon Hall", "Nicole Young", "Tyler King", "Rachel Green"
    ]
    
    patient_genders = ["male", "female"]
    duration_minutes = random.randint(10, 90)  # More variety in duration
    
    interview = MedicalInterviewDB(
        user_id=user_id,
        clinical_case_id=clinical_case_id,
        start_time=start_time,
        status=InterviewStatus.COMPLETED,
        patient_name=random.choice(patient_names),
        patient_gender=random.choice(patient_genders),
        personality_id=personality_id,
        total_duration=duration_minutes,
        end_time=start_time + timedelta(minutes=duration_minutes),
        interview_metadata={
            "mock_data": True, 
            "case_type": case_type,
            "conversation_style": random.choice(["thorough", "brief", "detailed", "focused"]),
            "patient_cooperation": random.choice(["excellent", "good", "moderate", "challenging"]),
            "interview_complexity": random.choice(["simple", "moderate", "complex"])
        }
    )
    session.add(interview)
    session.flush()  # Get the interview ID
    
    # Create messages (alternating between user and patient)
    messages = []
    user_questions = template["user_questions"].copy()
    patient_responses = template["patient_responses"].copy()
    
    # Randomize the order but ensure we have a good conversation flow
    random.shuffle(user_questions)
    random.shuffle(patient_responses)
    
    message_time = start_time
    message_count = min(len(user_questions), len(patient_responses), random.randint(6, 20))  # More variety in conversation length
    
    for i in range(message_count):
        # Add user question
        if i < len(user_questions):
            user_message = InterviewMessageDB(
                interview_id=interview.id,
                content=user_questions[i],
                sender_type=SenderType.USER.value,
                created_at=message_time,
                message_metadata={"message_order": i * 2, "intent": "question"}
            )
            session.add(user_message)
            messages.append(user_message)
            message_time += timedelta(seconds=random.randint(30, 120))
        
        # Add patient response
        if i < len(patient_responses):
            patient_message = InterviewMessageDB(
                interview_id=interview.id,
                content=patient_responses[i],
                sender_type=SenderType.PATIENT.value,
                created_at=message_time,
                message_metadata={"message_order": i * 2 + 1, "intent": "response"}
            )
            session.add(patient_message)
            messages.append(patient_message)
            message_time += timedelta(seconds=random.randint(30, 120))
    
    # Create user hypotheses
    hypotheses = template["hypotheses"].copy()
    random.shuffle(hypotheses)
    
    for i, hypothesis_text in enumerate(hypotheses[:random.randint(1, min(3, len(hypotheses)))]):  # Max 3 hypotheses due to constraint
        hypothesis = UserHypothesisDB(
            interview_id=interview.id,
            hypothesis_text=hypothesis_text,
            hypothesis_order=i + 1
        )
        session.add(hypothesis)
    
    # Create session notes
    notes = template["session_notes"].copy()
    random.shuffle(notes)
    
    for i, note_text in enumerate(notes[:random.randint(1, min(3, len(notes)))]):  # Max 3 notes for consistency
        note = MedicalSessionNoteDB(
            interview_id=interview.id,
            notes_content=note_text
        )
        session.add(note)
    
    # Create progress summary with more variety
    summary_templates = [
        f"Patient presented with symptoms consistent with {case_type}. Key findings include the reported symptoms and family history. Recommended further testing and follow-up.",
        f"Comprehensive interview conducted for {case_type} case. Patient was cooperative and provided detailed history. Multiple diagnostic considerations discussed.",
        f"Clinical interview focused on {case_type} symptoms. Patient reported significant impact on daily functioning. Differential diagnosis includes several possibilities.",
        f"Detailed assessment of {case_type} presentation. Patient's symptoms align with classic presentation. Further evaluation and monitoring recommended.",
        f"Patient interview revealed {case_type} symptoms with good patient cooperation. Family history and lifestyle factors discussed. Treatment options reviewed."
    ]
    
    progress_summary = ProgressSummaryDB(
        medical_interview_id=interview.id,
        summary_text=random.choice(summary_templates),
        age=random.randint(18, 85),  # Wider age range
        confidence_score=random.uniform(0.6, 0.95)  # More variety in confidence
    )
    session.add(progress_summary)
    
    # Create interview evaluation with more variety
    evaluation_categories = [
        {
            "category": "communication",
            "score": random.randint(6, 10),
            "feedback": random.choice([
                "Excellent communication skills with clear, empathetic questioning.",
                "Good interview technique with appropriate questions.",
                "Effective communication, though could improve follow-up questions.",
                "Adequate communication with room for improvement in patient rapport.",
                "Strong communication with good patient engagement."
            ])
        },
        {
            "category": "clinical_reasoning", 
            "score": random.randint(5, 10),
            "feedback": random.choice([
                "Strong clinical reasoning with systematic approach to diagnosis.",
                "Good clinical reasoning, consider exploring family history earlier.",
                "Adequate clinical reasoning with some areas for improvement.",
                "Clinical reasoning could be more systematic in approach.",
                "Excellent diagnostic thinking with comprehensive consideration of possibilities."
            ])
        },
        {
            "category": "completeness",
            "score": random.randint(5, 9),
            "feedback": random.choice([
                "Comprehensive interview covering all relevant areas.",
                "Patient was cooperative and provided detailed responses to questions.",
                "Good coverage of symptoms, could explore social history more.",
                "Adequate completeness with some areas needing more detail.",
                "Thorough interview with excellent patient cooperation."
            ])
        }
    ]
    
    evaluation = InterviewEvaluationDB(
        medical_interview_id=interview.id,
        evaluation_results=evaluation_categories,
        overall_score=random.randint(5, 10)  # Wider score range
    )
    session.add(evaluation)
    
    return interview

def seed_conversations():
    """Main function to seed mock conversations"""
    print("🌱 Starting conversation seeding...")
    
    # Create database connection
    database_url = get_database_url()
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with SessionLocal() as session:
        try:
            # Get existing users, clinical cases, and personalities
            users = session.query(UserDB).all()
            clinical_cases = session.query(ClinicalCaseDB).all()
            personalities = session.query(PersonalityDB).all()
            
            if not users:
                print("❌ No users found in database. Please seed users first.")
                return
            
            if not clinical_cases:
                print("❌ No clinical cases found in database. Please seed clinical cases first.")
                return
            
            print(f"📊 Found {len(users)} users, {len(clinical_cases)} clinical cases, {len(personalities)} personalities")
            
            # Show user roles
            print("👥 Users and their roles:")
            for user in users:
                print(f"   - {user.username}: {user.role.value}")
            
            # Create conversations for each user
            conversations_created = 0
            case_types = list(CONVERSATION_TEMPLATES.keys())
            
            for user in users:
                # Create 2-4 conversations per user
                num_conversations = random.randint(2, 4)
                
                for _ in range(num_conversations):
                    # Select random clinical case and personality
                    clinical_case = random.choice(clinical_cases)
                    personality = random.choice(personalities) if personalities else None
                    
                    # Map clinical case to conversation template with more variety
                    case_type = random.choice(list(CONVERSATION_TEMPLATES.keys()))  # Random case type for variety
                    
                    # Try to match case type to clinical case title if possible
                    title_lower = clinical_case.title.lower()
                    if "copd" in title_lower or "lung" in title_lower or "breathing" in title_lower:
                        case_type = "copd"
                    elif "diabetes" in title_lower or "sugar" in title_lower:
                        case_type = "diabetes"
                    elif "hypertension" in title_lower or "blood pressure" in title_lower or "pressure" in title_lower:
                        case_type = "hypertension"
                    elif "asthma" in title_lower or "wheezing" in title_lower:
                        case_type = "asthma"
                    elif "headache" in title_lower or "migraine" in title_lower or "pain" in title_lower:
                        case_type = "migraine"
                    elif "depression" in title_lower or "mood" in title_lower:
                        case_type = "depression"
                    elif "anxiety" in title_lower or "panic" in title_lower:
                        case_type = "anxiety"
                    elif "heart" in title_lower or "cardiac" in title_lower or "chest" in title_lower:
                        case_type = "heart_disease"
                    elif "thyroid" in title_lower or "hormone" in title_lower:
                        case_type = "thyroid"
                    elif "joint" in title_lower or "arthritis" in title_lower or "rheumatoid" in title_lower:
                        case_type = "arthritis"
                    
                    # Create the conversation
                    interview = create_mock_conversation(
                        session, 
                        user.id, 
                        clinical_case.id, 
                        personality.id if personality else None,
                        case_type
                    )
                    conversations_created += 1
                    
                    print(f"✅ Created conversation {conversations_created} for {user.role.value} {user.username} with case '{clinical_case.title}'")
            
            # Commit all changes
            session.commit()
            print(f"🎉 Successfully created {conversations_created} mock conversations!")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error seeding conversations: {e}")
            import traceback
            traceback.print_exc()
            raise

def create_additional_users():
    """Create additional users with different roles for testing"""
    print("👥 Creating additional users with different roles...")
    
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
            
            # Create additional users
            additional_users = [
                {
                    "username": "dr_smith",
                    "email": "dr.smith@example.com", 
                    "full_name": "Dr. Sarah Smith",
                    "role": "teacher",
                    "password": "password123"
                },
                {
                    "username": "student_john",
                    "email": "john.doe@example.com",
                    "full_name": "John Doe",
                    "role": "student",
                    "password": "password123"
                },
                {
                    "username": "student_maria",
                    "email": "maria.garcia@example.com",
                    "full_name": "Maria Garcia",
                    "role": "student",
                    "password": "password123"
                }
            ]
            
            created_count = 0
            for user_data in additional_users:
                # Check if user already exists
                result = conn.execute(text("SELECT id FROM users WHERE username = :username"), 
                                    {"username": user_data["username"]})
                existing_user = result.fetchone()
                
                if not existing_user:
                    # Create user with direct SQL
                    conn.execute(text("""
                        INSERT INTO users (username, email, full_name, hashed_password, disabled, preferred_language, role)
                        VALUES (:username, :email, :full_name, :hashed_password, :disabled, :preferred_language, :role)
                    """), {
                        "username": user_data["username"],
                        "email": user_data["email"],
                        "full_name": user_data["full_name"],
                        "hashed_password": pwd_context.hash(user_data["password"]),
                        "disabled": False,
                        "preferred_language": "en",
                        "role": user_data["role"]
                    })
                    created_count += 1
                    print(f"✅ Created {user_data['role']}: {user_data['username']}")
                else:
                    print(f"ℹ️  User already exists: {user_data['username']}")
            
            conn.commit()
            print(f"🎉 Created {created_count} additional users!")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error creating additional users: {e}")
            raise

def clear_existing_conversations():
    """Clear existing conversations (optional cleanup function)"""
    print("🧹 Clearing existing conversations...")
    
    database_url = get_database_url()
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with SessionLocal() as session:
        try:
            # Delete in reverse order of dependencies
            session.query(InterviewEvaluationDB).delete()
            session.query(ProgressSummaryDB).delete()
            session.query(MedicalSessionNoteDB).delete()
            session.query(UserHypothesisDB).delete()
            session.query(InterviewMessageDB).delete()
            session.query(MedicalInterviewDB).delete()
            
            session.commit()
            print("✅ Existing conversations cleared")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error clearing conversations: {e}")
            raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed mock conversations in the database")
    parser.add_argument("--clear", action="store_true", help="Clear existing conversations before seeding")
    parser.add_argument("--count", type=int, default=None, help="Number of conversations to create per user")
    parser.add_argument("--create-users", action="store_true", help="Create additional users with different roles")
    
    args = parser.parse_args()
    
    if args.create_users:
        create_additional_users()
    
    if args.clear:
        clear_existing_conversations()
    
    seed_conversations()
