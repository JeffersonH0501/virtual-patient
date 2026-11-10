import random

from app.core.functional_config import load_prompt, read_config_json, render_prompt

PERSONALITIES = read_config_json("personalities/profiles.json")


def format_when_to_show(when_to_show):
    """Format situational guidance based on when_to_show structure"""
    formatted = []
    for situation, guidance in when_to_show.items():
        situation_name = situation.replace('_', ' ').title()
        formatted.append(render_prompt("personalities/format_when_to_show",
            situation_name=situation_name,
            guidance=guidance,
        ))
    return "\n".join(formatted)

def get_subtle_personality_hints(personality_key, lang_code):
    """Get subtle personality hints without full dramatic traits"""
    personality = next(p for p in PERSONALITIES if p["key"] == personality_key)
    persona_info = personality["personality"]
    
    # Provide subtle hints based on personality type
    if personality_key == "elderly_forgetful":
        return "You might occasionally pause to think or tend to repeat yourself, but not dramatically"
    elif personality_key == "know_it_all":
        return "You might occasionally show confidence in your knowledge, but not arrogantly"
    elif personality_key == "rude_unfriendly":
        return "You are unfriendly and likes to be brief and direct"
    elif personality_key == "friendly_polite":
        return "You naturally show courtesy and cooperation, but not excessively"
    elif personality_key == "confused_inquisitive":
        return "You might ask for clarification when needed, but not excessively"
    elif personality_key == "skeptical_spiritual":
        return "You might occasionally mention lack of trust in conventional medicine, but not excessively"
    else:
        return "Just be yourself naturally"


def build_personality_prompt(personality_key, language, patient_name, patient_gender, conversation_history, message):
    """Build the complete personality prompt with gender agreement and patient name"""
    
    # Find the personality
    personality = next(p for p in PERSONALITIES if p["key"] == personality_key)
    persona_info = personality["personality"]
    
    # Randomly decide whether to apply strong personality based on personality's setting
    apply_strong_personality = random.random() < persona_info['apply_strong_personality']
    
    # Determine language code (es or en)
    lang_code = 'es' if 'es' in language.lower() or 'span' in language.lower() else 'en'
    
    # Gender guidance for Spanish
    gender_note = ""
    if lang_code == 'es':
        gender_note = render_prompt("personalities/gender_note",
            patient_gender=patient_gender,
            gender_form='feminine' if patient_gender.lower() in ['female', 'mujer', 'femenino'] else 'masculine',
            examples='cansada, confundida, enferma' if patient_gender.lower() in ['female', 'mujer', 'femenino'] else 'cansado, confundido, enfermo',
        )

    if apply_strong_personality:
        # Apply full personality with all traits and behaviors
        
        # Extract phrases already used to avoid repetition
        repetition_warning = ""
        if conversation_history:
            repetition_warning = load_prompt("personalities/repetition_warning")
        
        # Build optional response examples block only if patterns exist
        _patterns = (persona_info['response_patterns'].get(lang_code)
                     or persona_info['response_patterns'].get('en')
                     or [])
        response_examples_block = ""
        if len(_patterns) > 0:
            response_examples_block = render_prompt("personalities/response_examples",
                examples=chr(10).join((f'- {expr}' for expr in _patterns)),
            )

        prompt = render_prompt("personalities/strong",
            patient_name=patient_name,
            persona=personality['persona'],
            language=language,
            gender_note=gender_note,
            repetition_warning=repetition_warning,
            communication_style=persona_info['communication_style'],
            traits=chr(10).join((f"- {trait.replace('_', ' ').title()}: {value}" for trait, value in persona_info['traits'].items())),
            situations=format_when_to_show(persona_info['when_to_show']),
            response_examples_block=response_examples_block,
            history=conversation_history if conversation_history else 'Nothing yet - this is your first response',
            patient_gender=patient_gender,
            nonexpert='- Sound like a normal person having a conversation that is not an expert in medicine' if personality_key != 'know_it_all' else '',
            simplify="- ALWAYS change complex expressions to simpler ones (exacerbation -> worsening, however -> but, I have no knowledge -> I don't know, etc.)." if personality_key != 'know_it_all' else '',
            instructions=chr(10).join((f'- {instruction}' for instruction in persona_info['instructions'])),
            message=message,
        )
    else:
        # Just translate naturally with subtle personality hints
        subtle_hints = get_subtle_personality_hints(personality_key, lang_code)
        
        prompt = render_prompt("personalities/subtle",
            patient_name=patient_name,
            language=language,
            gender_note=gender_note,
            patient_gender=patient_gender,
            nonexpert='- Sound like a normal person having a conversation, do not use formal language, complex medical terms, or elaborate words' if personality_key != 'know_it_all' else '',
            simplify="- Change complex words to simpler ones (exacerbation -> worsening, however -> but, I have no knowledge -> I don't know)" if personality_key != 'know_it_all' else '',
            subtle_hints=subtle_hints,
            history=conversation_history if conversation_history else 'Nothing yet - this is your first response',
            message=message,
        )
    return prompt
