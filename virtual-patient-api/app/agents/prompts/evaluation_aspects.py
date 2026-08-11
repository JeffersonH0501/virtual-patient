
EVALUATION_ASPECTS = {
    'general_communication': [
        'The doctor greeted the patient in a way that made them feel comfortable.',
        'The doctor treated the patient with respect.',
        'The doctor listened to the patient without prejudice, regardless of appearance, manners, gender, race or way of speaking (No racist or sexist comments).',
        'The doctor maintained professionalism and emotional control, even when the patient behaved inappropriately or expressed disagreement.',
        'The doctor helped the patient understand what health changes to expect in the coming weeks or months.',
        'The doctor explained how the illness might affect the patient\'s ability to work or perform daily activities.',
        'The doctor helped relieve the patient\'s worries about being seriously ill.'
    ],
    
    'show_interest': [
        'The doctor showed interest in the patient\'s ideas about his/her health.',
        'The doctor showed genuine interest and concern for the patient.',
        'The doctor provided the patient with information about their concerns, whenever it was within their professional competence.',
        'The doctor was considerate of the patient\'s needs and prioritized them.'
    ],
    
    'show_empathy': [
        'The doctor understood the patient\'s main concerns about their health.',
        'The doctor explored the patient\'s emotions during the conversation.',
        'The doctor was friendly and kind toward the patient.',
        'The doctor responded appropriately to all the problems the patient mentioned.',
        'The doctor showed understanding toward the patient.',
        'The doctor was dedicated to helping the patient.'
    ],
    
    'speak_clearly': [
        'The doctor spoke in terms the patient could understand avoiding technical words.',
        'The doctor made sure the patient understood everything that was explained.',
        'The doctor expressed their opinions and recommendations clearly to the patient.',
        'The doctor explained the name of the illness using words the patient could understand.'
    ],
    
    'open_communication': [
        'The doctor gave the patient the opportunity to express what was really on their mind.',
        'The doctor respected the patient\'s right to speak freely.',
        'The doctor encouraged the patient to ask questions.'
    ],
    
    'completeness': [
        'The doctor obtained the current illnesses and its history.',
        'The doctor explored lifestyle aspects (diet, exercise, habits).',
        'The doctor asked about relevant medical history (chronic conditions, allergies, medications).',
        'The doctor recovered the patient\'s profession when it\'s relevant for the case.',
        'The doctor covered important information present in the clinical case.',
        'The hypotheses should be relevant to the clinical case information (symptoms, history, findings)',
        'The hypotheses should demonstrate logical reasoning based on the patient data',
        'The hypotheses should consider the most likely diagnoses given the case context'
    ]
}

EVALUATION_ASPECTS_ES = {
    'general_communication': [
        'El doctor saludó al paciente de una manera que lo hizo sentir cómodo.',
        'El doctor trató al paciente con respeto.',
        'El doctor escuchó al paciente sin prejuicios, independientemente de la apariencia, modales, género, raza o forma de hablar (Sin comentarios racistas o sexistas).',
        'El doctor mantuvo profesionalismo y control emocional, incluso cuando el paciente se comportó inapropiadamente o expresó desacuerdo.',
        'El doctor ayudó al paciente a entender qué cambios de salud esperar en las próximas semanas o meses.',
        'El doctor explicó cómo la enfermedad podría afectar la capacidad del paciente para trabajar o realizar actividades diarias.',
        'El doctor ayudó a aliviar las preocupaciones del paciente sobre estar gravemente enfermo.'
    ],
    
    'show_interest': [
        'El doctor mostró interés en las ideas del paciente sobre su salud.',
        'El doctor mostró interés genuino y preocupación por el paciente.',
        'El doctor proporcionó al paciente información sobre sus preocupaciones, siempre que estuvo dentro de su competencia profesional.',
        'El doctor fue considerado con las necesidades del paciente y las priorizó.'
    ],
    
    'show_empathy': [
        'El doctor entendió las principales preocupaciones del paciente sobre su salud.',
        'El doctor exploró las emociones del paciente durante la conversación.',
        'El doctor fue amigable y amable con el paciente.',
        'El doctor respondió apropiadamente a todos los problemas que el paciente mencionó.',
        'El doctor mostró comprensión hacia el paciente.',
        'El doctor se dedicó a ayudar al paciente.'
    ],
    
    'speak_clearly': [
        'El doctor habló en términos que el paciente podía entender, evitando palabras técnicas.',
        'El doctor se aseguró de que el paciente entendiera todo lo que se explicó.',
        'El doctor expresó sus opiniones y recomendaciones claramente al paciente.',
        'El doctor explicó el nombre de la enfermedad usando palabras que el paciente podía entender.'
    ],
    
    'open_communication': [
        'El doctor le dio al paciente la oportunidad de expresar lo que realmente tenía en mente.',
        'El doctor respetó el derecho del paciente a hablar libremente.',
        'El doctor alentó al paciente a hacer preguntas.'
    ],
    
    'completeness': [
        'El doctor obtuvo las enfermedades actuales y su historial.',
        'El doctor exploró aspectos del estilo de vida (dieta, ejercicio, hábitos).',
        'El doctor preguntó sobre el historial médico relevante (condiciones crónicas, alergias, medicamentos).',
        'El doctor recuperó la profesión del paciente cuando es relevante para el caso.',
        'El doctor cubrió información importante presente en el caso clínico.',
        'Las hipótesis deben ser relevantes para la información del caso clínico (síntomas, historial, hallazgos)',
        'Las hipótesis deben demostrar razonamiento lógico basado en los datos del paciente',
        'Las hipótesis deben considerar los diagnósticos más probables dado el contexto del caso'
    ]
}

def get_aspects_for_category(category: str) -> list:
    """Get evaluation aspects for a specific category and language"""
    return EVALUATION_ASPECTS.get(category, [])

def get_all_aspects(language: str = "en") -> dict:
    """Get all evaluation aspects for a specific language"""
    if language == "es":
        return EVALUATION_ASPECTS_ES
    return EVALUATION_ASPECTS

def format_aspects_for_prompt(category: str, numbered: bool = True) -> str:
    """Helper function to format aspects for prompts"""
    aspects = get_aspects_for_category(category)
    if numbered:
        return "\n".join([f"{i+1}. {aspect}" for i, aspect in enumerate(aspects)])
    else:
        return "\n".join([f"- {aspect}" for aspect in aspects])
