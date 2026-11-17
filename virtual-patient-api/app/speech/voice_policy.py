"""Patient voice selection independent from any speech provider."""


# Conversational voices that match the patient's gender; personalities differ by vocal style, not timbre.
PERSONALITY_VOICES = {
    "elderly_forgetful": {"male": "ballad", "female": "sage"},
    "know_it_all": {"male": "ash", "female": "coral"},
    "rude_unfriendly": {"male": "ash", "female": "coral"},
    "friendly_polite": {"male": "verse", "female": "shimmer"},
    "confused_inquisitive": {"male": "verse", "female": "sage"},
    "skeptical_spiritual": {"male": "ballad", "female": "shimmer"},
}

DEFAULT_VOICES = {
    "male": "ash",
    "female": "coral",
}


def select_patient_voice(
    personality_namespace_key: str | None = None,
    gender: str | None = None,
) -> str:
    """Select a stable provider voice from patient configuration."""
    normalized_gender = gender.lower() if gender else None
    if personality_namespace_key and normalized_gender:
        configured_voice = PERSONALITY_VOICES.get(
            personality_namespace_key,
            {},
        ).get(normalized_gender)
        if configured_voice:
            return configured_voice
    if normalized_gender:
        return DEFAULT_VOICES.get(normalized_gender, "alloy")
    return "alloy"
