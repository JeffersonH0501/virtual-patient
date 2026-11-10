"""Central application configuration sourced from the process environment."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


# Direct host execution may use the one local environment file at repository
# root. Docker injects the same variables and takes precedence.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPOSITORY_ROOT / ".env.local", override=False)

DEPLOYMENT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "deployment.json"
WORKER_TOKEN_FILE = Path("/run/secrets/video_processing_worker_token")
deployment = json.loads(DEPLOYMENT_CONFIG.read_text(encoding="utf-8"))
worker_token = (
    WORKER_TOKEN_FILE.read_text(encoding="utf-8").strip()
    if WORKER_TOKEN_FILE.is_file()
    else "local-video-processing-worker-token"
)


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENV", "development")

    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "virtual_patient")

    recaptcha_secret_key: str = os.getenv("RECAPTCHA_SECRET_KEY", "")
    secret_key: str = os.getenv("SECRET_KEY", "local-development-secret-change-me")
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    superuser_email: str = os.getenv("SUPERUSER_EMAIL", "").strip().lower()
    superuser_name: str = os.getenv("SUPERUSER_NAME", "").strip()
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

    video_processing_worker_url: str = os.getenv(
        "VIDEO_PROCESSING_WORKER_URL",
        "http://video-processing-worker:8010",
    ).rstrip("/")
    video_processing_worker_token: str = worker_token
    video_processing_worker_timeout_seconds: float = deployment["video_processing_worker_timeout_seconds"]

    # Temporary diagnostic timing logs for patient-response generation.
    # Hardcoded on purpose: not sourced from the environment. Flip to True in
    # code to emit the "patient_response_timing" logs while debugging latency.
    patient_response_timing_logging: bool = False
    media_retention_months: int = deployment["media_retention_months"]

    def __post_init__(self):
        if type(self.media_retention_months) is not int or not 1 <= self.media_retention_months <= 12:
            raise ValueError("Media retention must be between 1 and 12 calendar months")
        if type(self.video_processing_worker_timeout_seconds) not in (int, float) or not 0 < self.video_processing_worker_timeout_seconds < float("inf"):
            raise ValueError("Visual worker timeout must be a positive finite number of seconds")
        if self.environment.lower() in {"production", "prod"}:
            if self.recaptcha_secret_key.strip() in {"", "change-me"}:
                raise ValueError("Production requires RECAPTCHA_SECRET_KEY")
            if len(self.secret_key) < 32 or self.secret_key == "local-development-secret-change-me":
                raise ValueError("Production requires a non-default SECRET_KEY of at least 32 characters")
            if len(self.video_processing_worker_token) < 32 or self.video_processing_worker_token == "local-video-processing-worker-token":
                raise ValueError("Production requires a private video worker token of at least 32 characters")
            if self.superuser_password in {"", "local-superuser-change-me"}:
                raise ValueError("Production requires a deployment-managed superuser password")

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
