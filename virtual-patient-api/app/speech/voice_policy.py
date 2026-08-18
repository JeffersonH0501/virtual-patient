"""Patient voice selection independent from any speech provider."""


PERSONALITY_VOICES = {
    "elderly_forgetful": {"male": "onyx", "female": "echo"},
    "know_it_all": {"male": "onyx", "female": "nova"},
    "rude_unfriendly": {"male": "onyx", "female": "alloy"},
    "friendly_polite": {"male": "onyx", "female": "nova"},
    "confused_inquisitive": {"male": "onyx", "female": "nova"},
    "skeptical_spiritual": {"male": "echo", "female": "shimmer"},
}

DEFAULT_VOICES = {
    "male": "alloy",
    "female": "shimmer",
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
