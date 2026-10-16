"""Runtime configuration, loaded from environment variables (and `.env` locally)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import DataMode

__all__ = [
    "BlobBackend",
    "CatalogBackend",
    "DataMode",
    "JobBackend",
    "Settings",
    "StorageBackend",
    "get_settings",
]


class JobBackend(StrEnum):
    """How background jobs are executed (ADR-0006).

    `inline` runs jobs in-process. On Cloud Run with request-based CPU allocation
    (our free-credit setting) background work is throttled after the response is sent,
    so deployed environments use `pubsub`; `inline` is for local dev and tests.
    """

    INLINE = "inline"
    PUBSUB = "pubsub"


class StorageBackend(StrEnum):
    MEMORY = "memory"
    FIRESTORE = "firestore"


class CatalogBackend(StrEnum):
    SEED = "seed"  # data/catalog_seed/*.jsonl in memory (local, tests, demo fallback)
    BIGQUERY = "bigquery"


class BlobBackend(StrEnum):
    MEMORY = "memory"
    GCS = "gcs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "prod"] = "local"
    log_level: str = "INFO"

    # GCP
    gcp_project: str | None = None
    gcp_region: str = "us-central1"
    gcs_bucket: str | None = None
    bq_catalog_dataset: str = "catalog"

    # Backends
    storage_backend: StorageBackend = StorageBackend.MEMORY
    blob_backend: BlobBackend = BlobBackend.MEMORY
    catalog_backend: CatalogBackend = CatalogBackend.SEED
    catalog_seed_dir: Path = Path(__file__).resolve().parents[3] / "data" / "catalog_seed"
    job_backend: JobBackend = JobBackend.INLINE
    data_mode: DataMode = DataMode.CACHE_FIRST

    # Pub/Sub
    pubsub_topic: str = "analysis-jobs"
    pubsub_verify_oidc: bool = True
    pubsub_push_audience: str | None = None
    pubsub_push_service_account: str | None = None

    # LLM (Gemini on Vertex AI only; AI Studio keys are not covered by free credits)
    llm_enabled: bool = True
    gemini_flash_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    llm_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    copilot_max_tool_calls: int = Field(default=6, ge=1, le=20)

    # Distributor APIs for live data (P1, issue #12). Empty or unset = provider disabled.
    # SecretStr keeps values out of logs, reprs and error output.
    digikey_client_id: SecretStr | None = None
    digikey_client_secret: SecretStr | None = None
    digikey_sandbox: bool = False
    mouser_api_key: SecretStr | None = None
    element14_api_key: SecretStr | None = None
    element14_store: str = "in.element14.com"

    # HTTP
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def configured_distributors(self) -> list[str]:
        """Distributors whose credentials are present (blank values count as missing)."""

        def present(*values: SecretStr | None) -> bool:
            return all(v is not None and v.get_secret_value().strip() for v in values)

        return [
            name
            for name, ok in (
                ("DigiKey", present(self.digikey_client_id, self.digikey_client_secret)),
                ("Mouser", present(self.mouser_api_key)),
                ("element14", present(self.element14_api_key)),
            )
            if ok
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
