"""Gemini chat models on Vertex AI (never AI Studio keys: the free-trial credit only covers
Vertex AI). Returns None when LLM use is disabled, so callers must keep a deterministic
fallback (ADR-0002)."""

from enum import StrEnum

from langchain_core.language_models import BaseChatModel

from app.config import Settings


class ModelTier(StrEnum):
    FLASH = "flash"
    PRO = "pro"


def build_chat_model(
    settings: Settings, tier: ModelTier = ModelTier.FLASH, max_output_tokens: int | None = None
) -> BaseChatModel | None:
    if not settings.llm_enabled or not settings.gcp_project:
        return None

    from langchain_google_genai import ChatGoogleGenerativeAI

    model = settings.gemini_pro_model if tier is ModelTier.PRO else settings.gemini_flash_model
    return ChatGoogleGenerativeAI(
        model=model,
        vertexai=True,
        project=settings.gcp_project,
        location=settings.gcp_region,
        temperature=0,
        max_output_tokens=max_output_tokens or settings.llm_max_output_tokens,
        timeout=20,
        max_retries=1,
    )
