"""Chat models for the LLM edges (ADR-0002). Returns None when LLM use is disabled or not
configured, so callers must keep a deterministic fallback.

- vertex (deployed): Gemini on Vertex AI. Never AI Studio keys: the free-trial credit only
  covers Vertex AI.
- openrouter (local testing without GCP): OpenAI-compatible API, Gemini models by default.
"""

from enum import StrEnum

from langchain_core.language_models import BaseChatModel

from app.config import LlmProvider, Settings


class ModelTier(StrEnum):
    FLASH = "flash"
    PRO = "pro"


def build_chat_model(
    settings: Settings, tier: ModelTier = ModelTier.FLASH, max_output_tokens: int | None = None
) -> BaseChatModel | None:
    if not settings.llm_configured:
        return None
    max_tokens = max_output_tokens or settings.llm_max_output_tokens

    if settings.llm_provider is LlmProvider.OPENROUTER:
        assert settings.openrouter_api_key is not None  # guaranteed by llm_configured
        from langchain_openai import ChatOpenAI

        model = (
            settings.openrouter_pro_model
            if tier is ModelTier.PRO
            else settings.openrouter_flash_model
        )
        return ChatOpenAI(
            model=model,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0,
            timeout=30,
            max_retries=1,
            default_headers={"X-Title": "QuoteLens"},
            # OpenRouter's own field names (langchain would send max_completion_tokens).
            # Gemini 2.5 thinks before answering and those tokens count against the limit;
            # a low effort keeps most of the budget for the answer itself.
            extra_body={"max_tokens": max_tokens, "reasoning": {"effort": "low", "exclude": True}},
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    model = settings.gemini_pro_model if tier is ModelTier.PRO else settings.gemini_flash_model
    return ChatGoogleGenerativeAI(
        model=model,
        vertexai=True,
        project=settings.gcp_project,
        location=settings.gcp_region,
        temperature=0,
        max_output_tokens=max_tokens,
        timeout=20,
        max_retries=1,
    )
