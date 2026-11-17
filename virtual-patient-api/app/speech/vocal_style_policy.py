"""Provider-neutral paraverbal style policy for virtual patients."""

from app.speech.contracts import (
    DeliveryTone,
    HesitationFrequency,
    IntonationVariation,
    PauseFrequency,
    SpeakingRate,
    VocalEnergy,
    VocalStyle,
)


VOCAL_STYLE_POLICY_VERSION = "3"

# A slight slowdown reads as less rushed and more human. Mapped from the
# categorical speaking rate so the provider speed stays consistent with it.
_RATE_SPEED = {
    SpeakingRate.MODERATELY_SLOW: 0.92,
    SpeakingRate.MODERATE: 0.96,
    SpeakingRate.BRISK: 1.0,
}


def _style(
    profile_key: str,
    speaking_rate: SpeakingRate,
    pause_frequency: PauseFrequency,
    energy: VocalEnergy,
    intonation_variation: IntonationVariation,
    hesitation_frequency: HesitationFrequency,
    delivery_tone: DeliveryTone,
) -> VocalStyle:
    return VocalStyle(
        profile_key=profile_key,
        policy_version=VOCAL_STYLE_POLICY_VERSION,
        speaking_rate=speaking_rate,
        pause_frequency=pause_frequency,
        energy=energy,
        intonation_variation=intonation_variation,
        hesitation_frequency=hesitation_frequency,
        delivery_tone=delivery_tone,
        speed=_RATE_SPEED[speaking_rate],
    )


DEFAULT_VOCAL_STYLE = _style(
    profile_key="default",
    # Moderate pace with light hesitation reads as a real person describing
    # symptoms, not a brisk, fluent assistant.
    speaking_rate=SpeakingRate.MODERATE,
    pause_frequency=PauseFrequency.NATURAL,
    energy=VocalEnergy.MODERATE,
    intonation_variation=IntonationVariation.NATURAL,
    hesitation_frequency=HesitationFrequency.LIGHT,
    delivery_tone=DeliveryTone.NEUTRAL,
)


PERSONALITY_VOCAL_STYLES = {
    "elderly_forgetful": _style(
        profile_key="elderly_forgetful",
        speaking_rate=SpeakingRate.MODERATELY_SLOW,
        pause_frequency=PauseFrequency.OCCASIONAL,
        energy=VocalEnergy.LOW,
        intonation_variation=IntonationVariation.RESTRAINED,
        hesitation_frequency=HesitationFrequency.LIGHT,
        delivery_tone=DeliveryTone.REFLECTIVE,
    ),
    "know_it_all": _style(
        profile_key="know_it_all",
        speaking_rate=SpeakingRate.BRISK,
        pause_frequency=PauseFrequency.SPARSE,
        energy=VocalEnergy.HIGH,
        intonation_variation=IntonationVariation.EXPRESSIVE,
        hesitation_frequency=HesitationFrequency.NONE,
        delivery_tone=DeliveryTone.SELF_ASSURED,
    ),
    "rude_unfriendly": _style(
        profile_key="rude_unfriendly",
        speaking_rate=SpeakingRate.BRISK,
        pause_frequency=PauseFrequency.SPARSE,
        energy=VocalEnergy.MODERATE,
        intonation_variation=IntonationVariation.RESTRAINED,
        hesitation_frequency=HesitationFrequency.NONE,
        delivery_tone=DeliveryTone.IMPATIENT,
    ),
    "friendly_polite": _style(
        profile_key="friendly_polite",
        speaking_rate=SpeakingRate.BRISK,
        pause_frequency=PauseFrequency.NATURAL,
        energy=VocalEnergy.MODERATE,
        intonation_variation=IntonationVariation.EXPRESSIVE,
        hesitation_frequency=HesitationFrequency.NONE,
        delivery_tone=DeliveryTone.REASSURING,
    ),
    "confused_inquisitive": _style(
        profile_key="confused_inquisitive",
        speaking_rate=SpeakingRate.MODERATELY_SLOW,
        pause_frequency=PauseFrequency.FREQUENT,
        energy=VocalEnergy.MODERATE,
        intonation_variation=IntonationVariation.EXPRESSIVE,
        hesitation_frequency=HesitationFrequency.OCCASIONAL,
        delivery_tone=DeliveryTone.UNCERTAIN,
    ),
    "skeptical_spiritual": _style(
        profile_key="skeptical_spiritual",
        speaking_rate=SpeakingRate.MODERATELY_SLOW,
        pause_frequency=PauseFrequency.OCCASIONAL,
        energy=VocalEnergy.LOW,
        intonation_variation=IntonationVariation.RESTRAINED,
        hesitation_frequency=HesitationFrequency.LIGHT,
        delivery_tone=DeliveryTone.REFLECTIVE,
    ),
}


import hashlib
from dataclasses import replace

# Small, reversible per-turn nudges so consecutive replies do not share one
# uniform delivery. Each option stays within the natural range of the base style.
_RATE_NUDGE = {
    SpeakingRate.MODERATELY_SLOW: (SpeakingRate.MODERATELY_SLOW, SpeakingRate.MODERATE),
    SpeakingRate.MODERATE: (SpeakingRate.MODERATELY_SLOW, SpeakingRate.MODERATE, SpeakingRate.BRISK),
    SpeakingRate.BRISK: (SpeakingRate.MODERATE, SpeakingRate.BRISK),
}
_PAUSE_NUDGE = {
    PauseFrequency.SPARSE: (PauseFrequency.SPARSE, PauseFrequency.OCCASIONAL),
    PauseFrequency.NATURAL: (PauseFrequency.NATURAL, PauseFrequency.OCCASIONAL),
    PauseFrequency.OCCASIONAL: (PauseFrequency.NATURAL, PauseFrequency.OCCASIONAL, PauseFrequency.FREQUENT),
    PauseFrequency.FREQUENT: (PauseFrequency.OCCASIONAL, PauseFrequency.FREQUENT),
}


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256((text or "").encode("utf-8")).digest()[:4], "big")


def vary_vocal_style(style: VocalStyle, text: str | None) -> VocalStyle:
    """Deterministically nudge rate and pauses per reply, keyed on the text.

    The variation is derived from the text, so the same reply always synthesizes
    identically. This keeps replay and re-synthesis reproducible while avoiding a
    single uniform delivery across turns. It changes how the configured content
    is delivered, not what the patient says, and infers no psychological state.
    """
    if not text:
        return style
    seed = _seed(text)
    rate_options = _RATE_NUDGE[style.speaking_rate]
    pause_options = _PAUSE_NUDGE[style.pause_frequency]
    rate = rate_options[seed % len(rate_options)]
    pause = pause_options[(seed // 7) % len(pause_options)]
    return replace(style, speaking_rate=rate, pause_frequency=pause, speed=_RATE_SPEED[rate])


def select_patient_vocal_style(
    personality_namespace_key: str | None = None,
    text: str | None = None,
) -> VocalStyle:
    """Select configured acting directions without inferring patient state.

    When ``text`` is supplied, apply a deterministic per-turn variation so
    consecutive replies do not share one uniform delivery.
    """
    base = PERSONALITY_VOCAL_STYLES.get(personality_namespace_key, DEFAULT_VOCAL_STYLE) \
        if personality_namespace_key else DEFAULT_VOCAL_STYLE
    return vary_vocal_style(base, text)
