from pydantic import SecretStr

from app.config import Settings


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_distributors_need_non_blank_credentials() -> None:
    assert _settings().configured_distributors == []
    configured = _settings(
        digikey_client_id=SecretStr("id"),
        digikey_client_secret=SecretStr("secret"),
        mouser_api_key=SecretStr("  "),
        element14_api_key=SecretStr("key"),
    ).configured_distributors
    assert configured == ["DigiKey", "element14"]
    assert _settings(digikey_client_id=SecretStr("id")).configured_distributors == []


def test_secrets_never_appear_in_repr() -> None:
    settings = _settings(mouser_api_key=SecretStr("super-secret-value"))
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.model_dump())
