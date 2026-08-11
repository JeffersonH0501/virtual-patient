"""
Memory Tool Instructions for Virtual Patient Agent
Contains the detailed instructions for memory management tools
"""

MANAGE_MEMORY_INSTRUCTIONS = """MANDATORY: You MUST call this tool after every patient response to extract and store ALL medical information.

CRITICAL: Extract and store ALL relevant medical information from the patient's response. 
Analyze the response comprehensively and store:
- Symptoms (pain, discomfort, sensations, duration, intensity, patterns, triggers)
- Medications (current, past, dosages, side effects, compliance, frequency)
- Allergies (drugs, foods, environmental, reactions, severity)
- Family history (medical conditions in family members, genetic factors)
- Lifestyle factors (diet, exercise, sleep, stress, work, habits, social factors)
- Chronic conditions (diabetes, hypertension, etc., management, complications)
- Medical procedures (surgeries, tests, treatments, dates, outcomes)
- Social history (smoking, alcohol, drugs, occupation, living situation)
- Emotional/mental health information (mood, anxiety, depression, stress)
- Environmental factors (exposures, living conditions, occupational hazards)
- Risk factors (age, gender, family history, lifestyle)
- Quality of life factors (functional status, daily activities)
- Any other medically relevant information

Be exhaustive and don't miss any details that could be medically important.
Store information in a structured way that allows for easy retrieval and consistency checking.

YOU MUST CALL THIS TOOL AFTER EVERY PATIENT RESPONSE.

IMPORTANT: This tool should be called ONCE after the patient response. Do not call it multiple times or trigger additional responses."""

SEARCH_MEMORY_INSTRUCTIONS = """Search for ALL relevant patient information based on the current context.
Return comprehensive information about:
- Complete symptom history and characteristics (timeline, patterns, triggers)
- Full medication history and current regimen (compliance, side effects)
- Comprehensive family medical history (genetic patterns, risk factors)
- Detailed lifestyle and social factors (habits, environment, support)
- All previous medical conditions and treatments (outcomes, complications)
- Consistency with previous statements (check for contradictions)
- Emotional and mental health patterns
- Risk factors and preventive measures
- Any other relevant medical information

Provide complete context to ensure consistent and accurate responses.
Flag any inconsistencies or contradictions for review."""

BACKGROUND_LEARNING_INSTRUCTIONS = """
CRITICAL: Extract and store ALL relevant medical information from the patient's response. 
Analyze the response comprehensively and store:
- Symptoms (pain, discomfort, sensations, duration, intensity, patterns, triggers)
- Medications (current, past, dosages, side effects, compliance, frequency)
- Allergies (drugs, foods, environmental, reactions, severity)
- Family history (medical conditions in family members, genetic factors)
- Lifestyle factors (diet, exercise, sleep, stress, work, habits, social factors)
- Chronic conditions (diabetes, hypertension, etc., management, complications)
- Medical procedures (surgeries, tests, treatments, dates, outcomes)
- Social history (smoking, alcohol, drugs, occupation, living situation)
- Emotional/mental health information (mood, anxiety, depression, stress)
- Environmental factors (exposures, living conditions, occupational hazards)
- Risk factors (age, gender, family history, lifestyle)
- Quality of life factors (functional status, daily activities)
- Any other medically relevant information

Be exhaustive and don't miss any details that could be medically important.
Store information in a structured way that allows for easy retrieval and consistency checking.
""" 