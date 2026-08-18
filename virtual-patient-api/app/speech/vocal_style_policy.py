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


VOCAL_STYLE_POLICY_VERSION = "2"


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
    )


DEFAULT_VOCAL_STYLE = _style(
    profile_key="default",
    speaking_rate=SpeakingRate.BRISK,
    pause_frequency=PauseFrequency.NATURAL,
    energy=VocalEnergy.MODERATE,
    intonation_variation=IntonationVariation.NATURAL,
    hesitation_frequency=HesitationFrequency.NONE,
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


def select_patient_vocal_style(
    personality_namespace_key: str | None = None,
) -> VocalStyle:
    """Select configured acting directions without inferring patient state."""
    if not personality_namespace_key:
        return DEFAULT_VOCAL_STYLE
    return PERSONALITY_VOCAL_STYLES.get(
        personality_namespace_key,
        DEFAULT_VOCAL_STYLE,
    )
