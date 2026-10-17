from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import LlmProvider, Settings
from app.infra.llm import ModelTier, build_chat_model


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_no_model_without_configuration() -> None:
    assert build_chat_model(_settings()) is None
    assert build_chat_model(_settings(gcp_project="p", llm_enabled=False)) is None
    assert build_chat_model(_settings(llm_provider=LlmProvider.OPENROUTER)) is None
    blank = _settings(llm_provider=LlmProvider.OPENROUTER, openrouter_api_key=SecretStr(" "))
    assert build_chat_model(blank) is None


def test_openrouter_uses_its_own_model_ids_and_key() -> None:
    settings = _settings(
        llm_provider=LlmProvider.OPENROUTER, openrouter_api_key=SecretStr("sk-or-test")
    )
    flash = build_chat_model(settings, ModelTier.FLASH, max_output_tokens=300)
    pro = build_chat_model(settings, ModelTier.PRO)
    assert isinstance(flash, ChatOpenAI)
    assert isinstance(pro, ChatOpenAI)
    assert flash.model_name == "google/gemini-2.5-flash"
    assert pro.model_name == "google/gemini-2.5-pro"
    assert flash.extra_body is not None
    assert flash.extra_body["max_tokens"] == 300
    assert str(flash.openai_api_base) == "https://openrouter.ai/api/v1"
    assert "sk-or-test" not in repr(flash)


def test_vertex_is_the_default_provider() -> None:
    model = build_chat_model(_settings(gcp_project="p"), ModelTier.PRO)
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model.endswith("gemini-2.5-pro")
