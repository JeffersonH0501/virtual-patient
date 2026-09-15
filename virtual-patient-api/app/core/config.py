"""Central application configuration sourced from the process environment."""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


# Direct host execution may use the one local environment file at repository
# root. Docker injects the same variables and takes precedence.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPOSITORY_ROOT / ".env.local", override=False)


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENV", "development")

    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "virtual_patient")

    secret_key: str = os.getenv("SECRET_KEY", "local-development-secret-change-me")
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    superuser_email: str = os.getenv("SUPERUSER_EMAIL", "").strip().lower()
    superuser_first_name: str = os.getenv("SUPERUSER_FIRST_NAME", "").strip()
    superuser_last_name: str = os.getenv("SUPERUSER_LAST_NAME", "").strip()
    superuser_password: str = os.getenv("SUPERUSER_PASSWORD", "")
    superuser_preferred_language: str = os.getenv(
        "SUPERUSER_PREFERRED_LANGUAGE", "es"
    ).strip().lower()

    azure_openai_api_key: str | None = os.getenv("AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = os.getenv(
        "AZURE_OPENAI_API_VERSION",
        "2025-03-01-preview",
    )
    azure_openai_llm_deployment_name: str | None = os.getenv(
        "AZURE_OPENAI_LLM_DEPLOYMENT_NAME"
    )
    azure_openai_llm_mini_deployment_name: str | None = os.getenv(
        "AZURE_OPENAI_LLM_MINI_DEPLOYMENT_NAME"
    )
    azure_openai_stt_deployment_name: str | None = os.getenv(
        "AZURE_OPENAI_STT_DEPLOYMENT_NAME"
    )
    azure_openai_tts_deployment_name: str | None = os.getenv(
        "AZURE_OPENAI_TTS_DEPLOYMENT_NAME"
    )
    azure_openai_embedding_deployment_name: str | None = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"
    )

    media_storage_root: Path = Path(os.getenv("MEDIA_STORAGE_ROOT", str(REPOSITORY_ROOT / ".data" / "media")))
    media_retention_days: int | None = (
        int(os.environ["MEDIA_RETENTION_DAYS"])
        if os.getenv("MEDIA_RETENTION_DAYS", "").strip()
        else None
    )
    media_consent_policy_version: str = os.getenv(
        "MEDIA_CONSENT_POLICY_VERSION",
        "institutional-v1",
    )
    media_duration_tolerance_ms: int = int(
        os.getenv("MEDIA_DURATION_TOLERANCE_MS", "500")
    )
    media_min_free_bytes: int = int(
        os.getenv("MEDIA_MIN_FREE_BYTES", str(256 * 1024 * 1024))
    )
    patient_response_timing_logging: bool = os.getenv(
        "PATIENT_RESPONSE_TIMING_LOGGING",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    @property
    def database_url(self) -> str:
        password = quote_plus(self.postgres_password)
        user = quote_plus(self.postgres_user)
        database = quote_plus(self.postgres_db)
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:"
            f"{self.postgres_port}/{database}"
        )

    @property
    def azure_openai_v1_base_url(self) -> str:
        """Return the resource endpoint normalized for the OpenAI v1 API."""
        if not self.azure_openai_endpoint:
            return ""

        endpoint = self.azure_openai_endpoint.rstrip("/")
        if endpoint.endswith("/openai/v1"):
            return f"{endpoint}/"
        return f"{endpoint}/openai/v1/"


settings = Settings()
