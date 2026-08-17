#!/usr/bin/env python3
"""Explicit, billable smoke check for all configured Azure OpenAI deployments."""

from io import BytesIO
from pathlib import Path
import sys
from typing import Callable

from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.azure_openai import (  # noqa: E402
    EMBEDDING_DIMENSIONS,
    LLMVariant,
    create_chat_model,
    create_embeddings,
    create_openai_client,
)
from app.core.config import settings  # noqa: E402
from app.utils.tts_service import TTSService  # noqa: E402


def require_configuration() -> None:
    required = {
        "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
        "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
        "AZURE_OPENAI_LLM_DEPLOYMENT_NAME": (
            settings.azure_openai_llm_deployment_name
        ),
        "AZURE_OPENAI_LLM_MINI_DEPLOYMENT_NAME": (
            settings.azure_openai_llm_mini_deployment_name
        ),
        "AZURE_OPENAI_STT_DEPLOYMENT_NAME": (
            settings.azure_openai_stt_deployment_name
        ),
        "AZURE_OPENAI_TTS_DEPLOYMENT_NAME": (
            settings.azure_openai_tts_deployment_name
        ),
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME": (
            settings.azure_openai_embedding_deployment_name
        ),
    }
    missing = [name for name, value in required.items() if not value]
    placeholders = [
        name
        for name, value in required.items()
        if value
        and any(
            marker in value
            for marker in ("not-configured", "example.invalid", "change-me")
        )
    ]
    invalid = list(dict.fromkeys(missing + placeholders))
    if invalid:
        raise RuntimeError(
            "Configure real Azure values before this check: " + ", ".join(invalid)
        )


def check_chat(variant: LLMVariant) -> None:
    chat = create_chat_model(variant=variant, temperature=0)
    response = chat.invoke("Reply with exactly: azure-chat-ok")
    if "azure-chat-ok" not in str(response.content).lower():
        raise RuntimeError("Azure chat returned an unexpected response")


def check_embeddings() -> None:
    vector = create_embeddings().embed_query("azure-embedding-check")
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "Azure embedding deployment returned "
            f"{len(vector)} dimensions; expected {EMBEDDING_DIMENSIONS}"
        )


def check_tts() -> tuple[OpenAI, bytes]:
    client = create_openai_client()
    audio = TTSService(client=client).generate_audio(
        "Azure speech connection check.",
        voice="alloy",
    )
    if not audio:
        raise RuntimeError("Azure TTS returned no audio")
    return client, audio


def check_stt(client: OpenAI, audio: bytes) -> None:
    audio_file = BytesIO(audio)
    audio_file.name = "azure-speech-check.mp3"
    transcription = client.audio.transcriptions.create(
        model=settings.azure_openai_stt_deployment_name,
        file=audio_file,
    )
    if not getattr(transcription, "text", "").strip():
        raise RuntimeError("Azure STT returned an empty transcription")


def run_check(name: str, operation: Callable[[], None]) -> bool:
    try:
        operation()
    except Exception as error:  # noqa: BLE001 - smoke check must report every provider
        print(f"{name}: FAILED ({type(error).__name__}: {error})")
        return False
    print(f"{name}: OK")
    return True


def main() -> None:
    try:
        require_configuration()
    except RuntimeError as error:
        print(f"Azure configuration: FAILED ({error})")
        raise SystemExit(1) from None

    print("This command makes billable Azure OpenAI requests.")

    results = [
        run_check("Azure chat (normal)", lambda: check_chat(LLMVariant.NORMAL)),
        run_check("Azure chat (mini)", lambda: check_chat(LLMVariant.MINI)),
        run_check("Azure embeddings", check_embeddings),
    ]

    audio_client = None
    audio_data = None
    try:
        audio_client, audio_data = check_tts()
    except Exception as error:  # noqa: BLE001 - report and continue to summary
        print(f"Azure TTS: FAILED ({type(error).__name__}: {error})")
        results.append(False)
    else:
        print("Azure TTS: OK")
        results.append(True)

    if audio_client is None or audio_data is None:
        print("Azure STT: BLOCKED (TTS did not provide test audio)")
        results.append(False)
    else:
        results.append(
            run_check(
                "Azure STT",
                lambda: check_stt(audio_client, audio_data),
            )
        )

    if not all(results):
        raise SystemExit(1)
    print("All Azure OpenAI deployments passed the smoke check.")


if __name__ == "__main__":
    main()
