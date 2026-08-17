"""Central Azure OpenAI v1 clients used by the application."""

from enum import Enum
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from app.core.config import settings


EMBEDDING_DIMENSIONS = 1536


class LLMVariant(str, Enum):
    """Configured conversational model deployments."""

    NORMAL = "normal"
    MINI = "mini"


# Change this single constant to switch all application LLM workloads.
ACTIVE_LLM_VARIANT = LLMVariant.MINI


def _required(value: str | None, variable_name: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required Azure configuration: {variable_name}")
    return value


def deployment_for(variant: LLMVariant) -> str:
    """Resolve a model variant to its Azure deployment name."""
    if variant is LLMVariant.NORMAL:
        return _required(
            settings.azure_openai_llm_deployment_name,
            "AZURE_OPENAI_LLM_DEPLOYMENT_NAME",
        )
    if variant is LLMVariant.MINI:
        return _required(
            settings.azure_openai_llm_mini_deployment_name,
            "AZURE_OPENAI_LLM_MINI_DEPLOYMENT_NAME",
        )
    raise ValueError(f"Unsupported LLM variant: {variant}")


def _client_arguments() -> dict[str, str]:
    return {
        "api_key": _required(
            settings.azure_openai_api_key,
            "AZURE_OPENAI_API_KEY",
        ),
        "base_url": _required(
            settings.azure_openai_v1_base_url,
            "AZURE_OPENAI_ENDPOINT",
        ),
    }


def create_chat_model(
    *,
    variant: LLMVariant | None = None,
    **model_options: Any,
) -> ChatOpenAI:
    """Create a LangChain chat model against Azure's OpenAI-compatible v1 API."""
    selected_variant = variant or ACTIVE_LLM_VARIANT
    return ChatOpenAI(
        model=deployment_for(selected_variant),
        **_client_arguments(),
        **model_options,
    )


def create_embeddings() -> OpenAIEmbeddings:
    """Create the 1536-dimensional embedding client used by semantic memory."""
    return OpenAIEmbeddings(
        model=_required(
            settings.azure_openai_embedding_deployment_name,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
        ),
        dimensions=EMBEDDING_DIMENSIONS,
        **_client_arguments(),
    )


def create_openai_client() -> OpenAI:
    """Create the standard SDK client for Azure OpenAI v1 audio operations."""
    return OpenAI(**_client_arguments())
