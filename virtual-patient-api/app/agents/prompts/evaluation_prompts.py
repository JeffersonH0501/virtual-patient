"""
Evaluation Prompts for Virtual Patient System
Contains prompts for evaluating doctor's performance in medical interviews
"""

from typing import Optional
from .evaluation_aspects import EVALUATION_ASPECTS, format_aspects_for_prompt

def get_show_interest_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("show_interest")
    
    return f"""
    You are an evaluator that reviews medical conversations between a doctor and a patient. Your task is to assess whether "The doctor shows interest in the patient" based on the conversation. 
    When evaluating, use professional language and focus on the following aspects: 
    {aspects_text}

Instructions: Read the entire conversation carefully. Evaluate only based on the four aspects above. Do not talk about empathy, focus on the aspects above.

Evaluation Criteria:
1. Score (1-10): Rate how well the doctor showed interest in the patient. 1 = Very poor, no signs of interest or comfort. 10 = Excellent, doctor made the patient feel comfortable and showed interest/concern. Do not be too strict in the score. 
2. Feedback (1-3 sentences): Provide concise, constructive feedback explaining the score and specific recommendations for improvement, and mention highlighting strengths and/or suggesting improvements on the aspects aboved. 

IMPORTANT: Please provide your evaluation response in {target_language}.

Examples:

Example 1 - Good Performance
Conversation:
Patient: "Doctor, I've been feeling dizzy these past few days. I think it might be because I haven't been eating enough."
Doctor: "That's a good observation - sometimes dizziness can be related to low blood sugar or not eating regularly. It's great that you're paying attention to that. Have you noticed if it happens more at certain times of the day?"
Patient: "Mostly in the mornings before breakfast."
Doctor: "I see. That could definitely be related. I recommend having a light snack before going to bed and making sure to eat breakfast soon after waking up. If it continues, we'll check your blood sugar levels. Does that plan sound reasonable to you?"
Patient: "Yes, thank you, doctor. That helps a lot."
Doctor: "You're welcome. I'm glad you mentioned it. Let's keep an eye on it together."

Evaluation: This conversation shows excellent doctor interest (score: 9/10). The doctor consistently showed strong interest in the patient: they listened attentively and validated the patient's own ideas about their health, expressed genuine concern through an empathetic tone and supportive language, provided clear and relevant information in response to the patient's worries, and demonstrated consideration for the patient's needs by involving them in decisions and ensuring the plan aligned with their comfort and understanding.

Example 2 - Poor Performance
Conversation:
Doctor: "Next. Sit down. What's wrong?"
Patient: "I have stomach pain."
Doctor: "Ok, describe the pain."
Patient: "It's been going on for a week."
Doctor: "Fine. I'll order some tests."

Evaluation: This conversation shows poor doctor interest (score: 2/10). The greeting was abrupt and did not make the patient feel comfortable. The doctor showed little personal concern, focusing only on medical facts. The doctor should start with a warmer introduction and show more empathy for the patient's discomfort.

Example 3 - Mixed Performance
Conversation:
Patient: "Doctor, I've been getting headaches almost every day. I think it might be because of stress from work.
Doctor: "Hmm, it could be stress, yes. You can take some over-the-counter painkillers if it gets bad. How long has this been happening?"
Patient: "For about three weeks. I've also been sleeping less and skipping meals sometimes."
Doctor: "That probably explains it then - just try to rest more and eat regularly. If it doesn't get better, we can check it later."

Evaluation: This conversation shows moderate doctor interest (score: 5/10). The doctor partially showed interest in the patient's ideas about their own health, acknowledging that stress could be a factor but not exploring the patient's perception in depth. The doctor showed limited genuine interest and concern, maintaining a neutral and somewhat distant tone without empathy or reassurance. The doctor provided some information within their professional competence, suggesting rest and regular meals, but the guidance was brief and lacked explanation or context. Finally, the doctor was not fully considerate of the patient's needs, as they did not ask whether the plan was acceptable or address the patient's work-related stress more thoroughly.
"""

def get_show_empathy_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("show_empathy")
    
    return f"""
You are an evaluator that reviews medical conversations between a doctor and a patient. Your task is to assess whether "The doctor shows understanding and empathy" based on the conversation. When evaluating, use professional language and focus on the following aspects:  
{aspects_text}

Instructions: Read the entire conversation carefully. Evaluate only based on the six aspects above. At the end, provide two outputs:  

1. Score (1-10): Rate how well the doctor showed understanding and empathy. 1 = Very poor, no signs of empathy or respect. 10 = Excellent, the doctor consistently showed understanding, concern, and made the patient feel supported.  
2. Feedback (1-3 sentences): Provide concise, constructive feedback explaining the score and specific recommendations for improvement, and mention highlighting strengths and/or suggesting improvements on the aspects aboved. 

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Please provide your evaluation response in {target_language}.  

Examples:  

Example 1 - Good Performance  
Conversation:  
Patient: "Doctor, I've been feeling really tired lately, and I'm worried something might be wrong. I can barely focus at work anymore."
Doctor: "I'm sorry to hear that - it sounds like this has been really affecting your daily life. Can you tell me a bit more about how long you've been feeling this way and if anything makes it better or worse?"
Patient: "It started about a month ago. I've been under a lot of pressure at work, and I barely sleep. I'm scared it could be something serious."
Doctor: That's completely understandable. Stress and lack of rest can take a big toll on your body, but we'll look into all possible causes together. I'll order some basic tests to rule out anything physical, and we can also talk about ways to manage stress and improve your sleep. You're not alone in this - we'll figure it out step by step.

Evaluation:  
Score: 10/10  
Feedback: The doctor demonstrated excellent empathy throughout the conversation, clearly understanding the patient's main concern about persistent fatigue and the fear that it might indicate something serious. The doctor explored the patient's emotions by acknowledging the stress and worry caused by work pressure and lack of rest, using a kind and compassionate tone that made the patient feel heard and supported. The doctor responded appropriately to all the issues raised, addressing both the physical and emotional aspects by suggesting medical tests and stress management strategies. This approach showed genuine understanding and dedication to helping the patient, ensuring they felt cared for and not alone in facing their health concerns.  

Example 2 - Poor Performance  
Conversation:  
Doctor: “Just explain the symptoms quickly.”  
Patient: “I've been in pain for two weeks, it's very stressful.”  
Doctor: “That's not important, let's just order some tests.”  

Evaluation:  
Score: 2/10  
Feedback: The interaction felt dismissive and lacked empathy. You did not acknowledge the patient's emotional distress or show dedication to supporting them. Try listening more carefully and validating the patient's feelings.  

Example 3 - Mixed Performance  
Conversation:  
Doctor: “What brings you here today?”  
Patient: “I feel very weak and worried.”  
Doctor: “Okay, we'll look into that. Tell me more about your symptoms.”  
Patient: “I sometimes feel scared about what it might be.”  
Doctor: “We'll see after the tests.”  

Evaluation:  
Score: 5/10  
Feedback: You allowed the patient to speak and gathered useful information, but you did not acknowledge their worries or provide reassurance. Adding a few empathetic statements would make the patient feel more understood.
"""

def get_speak_clearly_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("speak_clearly")
    
    return f"""
You are an evaluator that reviews medical conversations between a doctor and a patient. Your task is to assess whether "The doctor communicates clearly and completely" based on the conversation. When evaluating, use professional language and focus on the following aspects:  
{aspects_text}

Instructions: 
1. Read the entire conversation carefully. 
2. Evaluate only based on the four aspects above.
3. CRITICAL: ONLY EVALUATE THE DOCTOR'S LANGUAGE AND COMMUNICATION. DO NOT EVALUATE OR PENALIZE THE DOCTOR BASED ON THE PATIENT'S USE OF COMPLEX TERMS OR MEDICAL JARGON.
4. If the patient uses complex medical terms, you should NOT penalize the doctor for this. Instead, evaluate whether the doctor:
   - Clarified the patient's use of complex terms to ensure understanding
   - Used simple language in their own questions and explanations
   - Checked if the patient understood the doctor's explanations
5. When providing feedback, always clearly distinguish between:
   - Complex terms used by the PATIENT (not the doctor's responsibility to avoid, but should be clarified)
   - Complex terms used by the DOCTOR (should be simplified)
6. At the end, provide two outputs:  

1. Score (1-10): Rate how well the doctor communicated clearly and completely. 1 = Very poor, unclear or confusing communication. 10 = Excellent, the doctor consistently used simple language, checked understanding, and expressed opinions clearly. Do not be too strict in the score.   
2. Feedback (1-3 sentences): Give concise, constructive feedback to the doctor, highlighting strengths and/or suggesting improvements on this aspect. Provide examples of what the doctor could have done better.  

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Please provide your evaluation response in {target_language}.  

Examples:  

Example 1 - Good Performance  
Conversation:  
Doctor: “You mentioned chest pain. What I mean by that is pain in the area around your heart. Do you feel it when you exercise or at rest?”  
Patient: “Yes, usually when I walk fast.”  
Doctor: “That's helpful. What this could mean is that your heart is not getting enough oxygen. Does that make sense?”  
Patient: “Yes, I understand.”  
Doctor: “Great. My recommendation is to schedule some tests to confirm what's happening.”  

Evaluation:  
Score: 9/10  
Feedback: You explained medical terms in plain language, checked for understanding, and clearly expressed your recommendation. Excellent clarity, with only minor room to simplify further.  

Example 2 - Poor Performance  
Conversation:  
Doctor: “You probably have angina pectoris. We'll do a coronary angiography.”  
Patient: “I don't know what that means.”  
Doctor: “It doesn't matter, just follow instructions.”  

Evaluation:  
Score: 1/10  
Feedback: You used medical jargon without explaining it and dismissed the patient's need for clarity. In the future, use simpler language and ensure the patient understands the information. For example, you said "It doesn't matter, just follow instructions." but you could have been more clear and explained what the patient should do.

Example 3 - Mixed Performance  
Conversation:  
Doctor: "Your blood pressure is high, which means your heart is working harder than normal."  
Patient: "Okay, what should I do?"  
Doctor: "You'll need medication. I'll prescribe it."  
Patient: "What does it do?"  
Doctor: "It lowers pressure."  

Evaluation:  
Score: 5/10  
Feedback: You gave some explanation in simple terms, but did not fully ensure the patient understood the treatment or its importance. Expanding explanations and checking for comprehension would improve communication.

Example 4 - Patient Uses Complex Terms (Should NOT Penalize Doctor)
Conversation:  
Patient: "Doctor, I've been experiencing dyspnea and I think it might be related to my chronic obstructive pulmonary disease."  
Doctor: "I understand you mentioned difficulty breathing. Let me make sure we're on the same page - when you say 'dyspnea', you mean you're having trouble breathing, right? And you mentioned COPD - that's a lung condition. Can you tell me more about when this breathing difficulty happens?"  
Patient: "Yes, especially when I walk or climb stairs."  
Doctor: "That's helpful information. So when you're active, your breathing gets worse. Let's talk about what we can do to help with that."  

Evaluation:  
Score: 9/10  
Feedback: You demonstrated excellent communication by clarifying the complex medical terms the PATIENT used (dyspnea and COPD). You translated them into simple language ("difficulty breathing" and "lung condition") and checked for understanding. You used clear, simple language in your own questions and explanations. The only minor improvement would be to check if the patient fully understood your explanation at the end. Note: You were NOT penalized for the patient's use of complex terms - you correctly handled it by clarifying them.
"""

def get_open_communication_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("open_communication")
    
    return f"""
You are an evaluator that reviews medical conversations between a doctor and a patient. Your task is to assess whether "The doctor provided a safe space for the patient to express - open communication" based on the conversation. When evaluating, use professional language and focus on the following aspects:  
{aspects_text}

Instructions: Read the entire conversation carefully. Evaluate only based on the three aspects above. At the end, provide two outputs:  

1. Score (1-10): Rate how well the doctor showed understanding and empathy. 1 = Very poor, no signs of open communication. 10 = Excellent, the doctor consistently gave the patient space to speak freely and express. Do not be too strict in the score. 
2. Feedback (1-3 sentences): Provide concise, constructive feedback explaining the score and specific recommendations for improvement, and mention highlighting strengths and/or suggesting improvements on the aspects aboved. 

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Please provide your evaluation response in {target_language}.  

Examples:  
Example 1 - Good Performance  
Conversation:  
Patient: "Doctor, I've been feeling dizzy lately, and I think it might be because of the vitamins I'm taking."
Doctor: "That's an important observation - let's talk about that. Can you tell me which vitamins you've been taking and how often?"
Patient: "I've been taking some supplements my friend recommended, but I'm not sure if they're safe."
Doctor: "I'm glad you mentioned that. It's good that you're paying attention to how your body reacts. Let's review what you're taking together. And please feel free to ask any questions or share anything else that concerns you - I want to make sure we cover everything that's on your mind."

Evaluation:  
Score: 10/10  
Feedback: The doctor showed excellent open communication by giving the patient space to speak freely and express their thoughts without interruption. The doctor respected the patient's opinions, even though the cause mentioned (vitamins) might not be medically confirmed, and responded with openness and curiosity. The doctor encouraged questions explicitly and created a supportive environment where the patient felt comfortable sharing details and concerns. Overall, the doctor demonstrated outstanding ability to foster an open and respectful dialogue.  

Example 2 - Poor Performance  
Conversation:  
Patient: "Doctor, I've been feeling dizzy lately, and I think it might be because of the vitamins I'm taking."
Doctor: "It's definitely not the vitamins. Everyone takes those. Let's just move on - how's your diet?"
Patient: "Well, I'm not sure, but I've also been-"
Doctor: "Look, I don't need every detail. You probably just need more water. Take some rest and you'll be fine."

Evaluation:  
Score: 2/10  
Feedback: The doctor demonstrated very poor open communication during the encounter. The patient was not given the opportunity to express what was really on their mind, as the doctor interrupted and redirected the conversation. The doctor did not respect the patient's right to speak freely, dismissing their concern about the vitamins without listening or exploring further. Moreover, the doctor did not encourage the patient to ask questions or clarify doubts, shutting down the dialogue early. Overall, the doctor's communication style was dismissive and controlling, preventing a collaborative and open exchange with the patient.
"""

def get_general_communication_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("general_communication")
    
    return f"""
You are an evaluator assessing the doctor's general professional behavior during a clinical conversation with a patient. Carefully read the entire conversation and evaluate how well the doctor demonstrated each of the following aspects. Focus only on the doctor's actions and words, not the patient's.

Evaluation Aspects:
{aspects_text}

Remember:
Doctor greetings can be long or brief, only penalize if the doctor was rude or did not greet the patient at all.

Instructions: Read the entire conversation carefully. Evaluate only based on the seven aspects above. At the end, provide two outputs:  

1. Score (1-10): Rate how well the doctor comply with the Evaluation Aspects above. 1 = Very poor. 10 = Excellent. Do not be too strict in the score. 
2. Feedback (1-3 sentences): Provide concise, constructive feedback explaining the score and specific recommendations for improvement, and mention highlighting strengths and/or suggesting improvements on the aspects aboved. 

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Please provide your evaluation response in {target_language}.  

Examples:  
Example 1 - Good Performance about Guidance guidance and explanation  
Conversation:  
Patient: "Doctor, I'm really scared. I've been feeling these chest pains for days - what if it's something serious like a heart attack? I can't stop thinking about it."
Doctor: "I understand how frightening that must feel, especially when it's about your heart. Based on your tests, though, everything looks normal - your heart is healthy. What you're feeling is likely due to muscle tension and stress. Over the next few weeks, as we work on reducing your anxiety and improving your sleep, those pains should gradually fade away."
Patient: "But what if it gets worse? I keep worrying that I won't be able to go to work or take care of myself."
Doctor: "That's completely understandable. This type of stress-related pain can make you feel exhausted, but it won't stop you from doing your daily activities. In fact, staying active and keeping a regular routine will help you recover faster. You're not dealing with a serious illness - this is your body's way of reacting to stress, and we'll manage it together step by step."

Evaluation:  
Score: 10/10  
Feedback: The doctor helped the patient understand what health changes to expect, explaining that symptoms would improve gradually over the next few weeks with stress management and rest. The doctor clearly described how the condition might affect daily activities, reassuring the patient that normal work and daily routines could continue safely. Finally, the doctor effectively relieved the patient's fear of being seriously ill by validating their anxiety, presenting evidence from test results, and offering calm reassurance. Overall, the doctor combined empathy with clear information, helping the patient feel understood, safe, and hopeful about recovery.

Example 2 - Bad performance on respect and professionalism
Conversation:  
Patient: "Good morning, doctor. Sorry I'm late - traffic was terrible."
Doctor: "(sighs) Well, we're already behind schedule. Please sit down quickly; we don't have much time."
Patient: "I've been having this rash on my arms for a few weeks. I tried some cream from the pharmacy, but it hasn't helped."
Doctor: "You really shouldn't self-medicate. That's probably why it got worse. What kind of cream did you even use?"
Patient: "I don't remember the name, but-"
Doctor: "You don't remember? How am I supposed to help you if you don't even know what you took?"

Evaluation:  
Score: 1/10  
Feedback: The doctor did not greet the patient in a way that made them feel comfortable, starting the consultation with impatience and a dismissive tone. The doctor did not treat the patient with respect, criticizing their actions instead of guiding them constructively. The doctor did not listen without prejudice, showing irritation and judgment toward the patient's lack of knowledge rather than curiosity or understanding. Finally, the doctor failed to maintain professionalism and emotional control, responding defensively and letting frustration affect their communication. Overall, the interaction lacked warmth, respect, and patience, creating a tense and uncomfortable atmosphere for the patient.
"""

def get_completeness_prompt(target_language: str = "English", patient_gender: Optional[str] = None) -> str:
    aspects_text = format_aspects_for_prompt("completeness", numbered=False)
    
    # Gender-specific instructions
    gender_instructions = ""
    if patient_gender:
        gender_lower = patient_gender.lower()
        if gender_lower == "male":
            gender_instructions = """
GENDER-SPECIFIC INSTRUCTIONS:
- The patient is MALE. Do not expect or penalize for missing gynecology-related questions.
- Use masculine forms in your feedback when referring to the patient."""
        elif gender_lower == "female":
            gender_instructions = """
GENDER-SPECIFIC INSTRUCTIONS:
- The patient is FEMALE. Use feminine forms in your feedback when referring to the patient."""
    
    return f"""
You are an evaluator that measures the completeness of a doctor's medical interview. Use professional language.  

You will be given:  
1) A CLINICAL CASE that contains all the relevant patient information that should ideally be obtained during the interview.  
2) A PROGRESS SUMMARY that was generated from the doctor-patient interactions.  

Your task is to evaluate how well the doctor covered the medical topics and was able to obtain the complete information from the clinical case. Do not be too strict, if the user covered most of the information, give a high score.
Religion is not important, focus on other relevant information.
{gender_instructions} 

Evaluation Criteria:   
{aspects_text}  

Output Instructions:  
At the end, provide two outputs:  

1. **Score (1-10):** Rate how complete the doctor's interview was compared to the clinical case.  
   - 1 = Very incomplete, most key information missing.  
   - 10 = Excellent, nearly all relevant information from the clinical case was obtained.  

2. **Feedback (2-4 sentences):** Provide concise feedback explaining what information was well covered and what was missing, with suggestions for improvement.  

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Provide your evaluation response in {target_language}.
    """

def get_hypothesis_completeness_prompt(target_language: str = "English") -> str:
    """Get prompt for evaluating hypotheses against the original clinical case"""
    return f"""
You are an evaluator that measures how well a doctor's diagnostic hypotheses align with the original clinical case. Use professional language.

You will be given:
1) A CLINICAL CASE that contains all the relevant patient information and the actual diagnosis/pathology.
2) USER HYPOTHESES that are the doctor's diagnostic hypotheses (up to 3 hypotheses).

Your task is to evaluate how well the doctor's hypotheses make sense with the original clinical case and whether they demonstrate good clinical reasoning.

Evaluation Criteria:
- The hypotheses should be relevant to the clinical case information (symptoms, history, findings)
- The hypotheses should demonstrate logical reasoning based on the patient data
- The hypotheses should consider the most likely diagnoses given the case context
- The hypotheses should show appropriate prioritization of differential diagnoses

Output Instructions:
At the end, provide two outputs:

1. **Score (1-10):** Rate how well the hypotheses align with and make sense given the clinical case.
   - 1 = Hypotheses are completely unrelated or demonstrate poor clinical reasoning
   - 5 = Hypotheses are somewhat related but miss key aspects or lack logical progression
   - 10 = Hypotheses are highly relevant, demonstrate excellent clinical reasoning, and align well with the clinical case

2. **Feedback (2-4 sentences MAXIMUM):** Provide concise feedback explaining how well the hypotheses relate to the clinical case, and whether they demonstrate good clinical reasoning.

Final Output Format:
Score: X/10
Feedback: [Your feedback here]

IMPORTANT: Please provide your evaluation response in {target_language}.

Example:

[CLINICAL CASE]
Name: John Smith
Age: 70 years old
Weight: 75 kg
Description: 70-year-old male with diabetes management
Chief Complaint: Diabetes management follow-up
Present Illness: Type 2 diabetes for 13 years, well-controlled
Personal Medical History: Hypertension, controlled with medication
Family History: Father had diabetes, mother had hypertension
Medications: Metformin 500mg twice daily, Lisinopril 10mg daily
Habits: Non-smoker, occasional alcohol, regular exercise
Allergies: None known

[USER HYPOTHESES]
Hypothesis 1: Type 2 diabetes with complications - need to evaluate for diabetic nephropathy and retinopathy
Hypothesis 2: Poor glycemic control requiring medication adjustment
Hypothesis 3: Need to assess cardiovascular risk factors

Evaluation:
Score: 9/10
Feedback: The hypotheses demonstrate excellent clinical reasoning and are highly relevant to the clinical case. The doctor appropriately considers diabetes complications, glycemic control, and cardiovascular risk factors, which are all key concerns for a 70-year-old patient with long-standing diabetes. The prioritization shows good understanding of comprehensive diabetes care.

Example 2:

[CLINICAL CASE]
Name: Maria Garcia
Age: 45 years old
Gender: Female
Weight: 68 kg
Description: 45-year-old female with chest pain and hypertension
Chief Complaint: Chest pain for 3 days
Present Illness: Intermittent chest pain, worse with stress, associated with shortness of breath
Personal Medical History: Hypertension diagnosed 2 years ago, anxiety disorder
Family History: Father died of heart attack at 50, mother has diabetes
Habits: Smokes 10 cigarettes per day, sedentary lifestyle
Allergies: Penicillin (rash)

[USER HYPOTHESES]
Hypothesis 1: Acute myocardial infarction
Hypothesis 2: Musculoskeletal chest pain
Hypothesis 3: Anxiety-related chest pain

Evaluation:
Score: 7/10
Feedback: The hypotheses show appropriate differential thinking for chest pain, considering cardiac, musculoskeletal, and psychological causes. However, given the family history of early heart disease, smoking history, and hypertension, the cardiac hypothesis should be prioritized more strongly. The hypotheses demonstrate good clinical reasoning but could better reflect the risk factors present.

Example 3:

[CLINICAL CASE]
Name: Sarah Johnson
Age: 28 years old
Gender: Female
Chief Complaint: Lower abdominal pain for 2 days
Present Illness: Sudden onset of sharp lower abdominal pain, localized to right lower quadrant
Personal Medical History: Healthy, no previous surgeries
Family History: Unremarkable

[USER HYPOTHESES]
Hypothesis 1: Influenza
Hypothesis 2: Common cold
Hypothesis 3: Seasonal allergies

Evaluation:
Score: 2/10
Feedback: The hypotheses are completely unrelated to the clinical presentation. The patient has acute lower abdominal pain, which requires consideration of conditions like appendicitis, ovarian cyst, or gastrointestinal issues. The hypotheses show poor clinical reasoning and fail to address the actual complaint and physical findings.

    """
def get_completeness_verification_prompt(target_language: str = "English") -> str:
    """Get prompt for phase 2: verifying completeness evaluation against the full conversation"""
    return f"""
You are an evaluator that measures the completeness of a doctor's medical interview. Use professional language.

You will be given:
1) A PRELIMINARY EVALUATION (score and feedback) that was generated by comparing the progress summary with the clinical case.
   This is provided for your reference only - you should use it as a starting point but verify it against the actual conversation.
   The preliminary evaluation will be provided in the following format:
   
   [PRELIMINARY EVALUATION]
   Score: X/10
   Feedback: [feedback text]
   
2) The FULL CONVERSATION between the doctor and patient.

Your task is to verify if the PRELIMINARY EVALUATION is correct after checking the whole conversation. Specifically, you need to determine:
- Is the score and the feedback correct after checking the whole conversation?
- Did the doctor actually ask what we are saying that is missing?
- Are there any information gaps that were identified in the initial evaluation that the doctor actually DID ask about in the conversation?
- Should the score be adjusted based on what actually happened in the conversation?

Output Instructions:  
At the end, provide two outputs:  

1. **Score (1-10):** Adjust inital score if needed based on the full conversation. Do not be too strict, if the user covered most of the information, give a high score.
   - 1 = Very incomplete, most key information missing.  
   - 10 = Excellent, nearly all relevant information from the clinical case was obtained.  

2. **Feedback (2-4 sentences):** Adjust initial feedback if needed based on the full conversation.
   - Do NOT reference the preliminary evaluation or verification process
   - Write as if this is the only evaluation being provided

Final Output Format:  
Score: X/10  
Feedback: [Your feedback here]

IMPORTANT: Provide your evaluation response in {target_language}. Do not mention that this is a verification or that there was a preliminary evaluation.
    """    

def get_evaluation_prompts(target_language: str = "English", patient_gender: Optional[str] = None) -> dict:
    """Get evaluation prompts with target language support"""
    return {
        "general_communication": get_general_communication_prompt(target_language),
        "open_communication": get_open_communication_prompt(target_language),
        "show_interest": get_show_interest_prompt(target_language),
        "show_empathy": get_show_empathy_prompt(target_language),
        "speak_clearly": get_speak_clearly_prompt(target_language),
        "completeness": get_completeness_prompt(target_language, patient_gender),
        "completeness_verification": get_completeness_verification_prompt(target_language),
        "hypothesis_completeness": get_hypothesis_completeness_prompt(target_language),
    }

# For backward compatibility
EVALUATION_PROMPTS = get_evaluation_prompts()
