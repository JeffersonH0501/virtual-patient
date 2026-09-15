"""Azure AI Speech Avatar SSML generation adhering to the vocal style policy."""

import html
from typing import Optional

from app.core.config import settings
from app.speech.contracts import (
    DeliveryTone,
    SpeakingRate,
    VocalEnergy,
    VocalStyle,
)
from app.speech.vocal_style_policy import select_patient_vocal_style

# High-quality Latin American neural voices for Spanish clinical interviews
AZURE_AVATAR_VOICES = {
    "female": "es-CO-SalomeNeural",
    "male": "es-CO-GonzaloNeural",
}

# Prebuilt Azure Speech Avatar characters
AZURE_AVATAR_CHARACTERS = {
    "female": "lisa",
    "male": "max",
}


def select_avatar_voice(gender: Optional[str] = None) -> str:
    """Select appropriate Azure Neural Voice for the patient."""
    normalized_gender = (gender or "").lower().strip()
    if normalized_gender in {"female", "mujer", "femenino", "f"}:
        return AZURE_AVATAR_VOICES["female"]
    return AZURE_AVATAR_VOICES["male"]


def select_avatar_character(gender: Optional[str] = None) -> str:
    """Select standard Azure Speech Avatar character matching patient gender."""
    normalized_gender = (gender or "").lower().strip()
    if normalized_gender in {"female", "mujer", "femenino", "f"}:
        return settings.azure_speech_avatar_character_female
    return settings.azure_speech_avatar_character_male


def select_avatar_style(gender: Optional[str] = None) -> str:
    """Select a real-time style supported by the selected standard avatar."""
    normalized_gender = (gender or "").lower().strip()
    if normalized_gender in {"female", "mujer", "femenino", "f"}:
        return "casual-sitting"
    return "casual"


def render_avatar_ssml(
    text: str,
    vocal_style: Optional[VocalStyle] = None,
    gender: Optional[str] = None,
    voice_name: Optional[str] = None,
) -> str:
    """Build compliant SSML with Azure Speech prosody derived from VocalStyle."""
    voice = voice_name or select_avatar_voice(gender)
    style = vocal_style or select_patient_vocal_style()

    # Map speaking rate
    rate_map = {
        SpeakingRate.MODERATELY_SLOW: "-15%",
        SpeakingRate.MODERATE: "0%",
        SpeakingRate.BRISK: "+10%",
    }
    rate = rate_map.get(style.speaking_rate, "0%")

    # Map vocal energy to volume and subtle pitch
    energy_map = {
        VocalEnergy.LOW: ("soft", "-3%"),
        VocalEnergy.MODERATE: ("medium", "0%"),
        VocalEnergy.HIGH: ("loud", "+4%"),
    }
    volume, pitch = energy_map.get(style.energy, ("medium", "0%"))

    # Map delivery tone to express-as style where appropriate
    style_tag_open = ""
    style_tag_close = ""
    if style.delivery_tone == DeliveryTone.REASSURING:
        style_tag_open = '<mstts:express-as style="friendly" styledegree="1.2">'
        style_tag_close = "</mstts:express-as>"
    elif style.delivery_tone == DeliveryTone.REFLECTIVE:
        style_tag_open = '<mstts:express-as style="calm" styledegree="1.1">'
        style_tag_close = "</mstts:express-as>"
    elif style.delivery_tone == DeliveryTone.IMPATIENT:
        style_tag_open = '<mstts:express-as style="disgruntled" styledegree="1.1">'
        style_tag_close = "</mstts:express-as>"
    elif style.delivery_tone == DeliveryTone.SELF_ASSURED:
        style_tag_open = '<mstts:express-as style="cheerful" styledegree="1.0">'
        style_tag_close = "</mstts:express-as>"

    escaped_text = html.escape(text.strip())

    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="es-CO">'
        f'<voice name="{voice}">'
        f"{style_tag_open}"
        f'<prosody rate="{rate}" pitch="{pitch}" volume="{volume}">'
        f"{escaped_text}"
        f"</prosody>"
        f"{style_tag_close}"
        f"</voice></speak>"
    )

