"""Settings are the single place runtime configuration enters the app."""

from atsc.config import Settings


def test_deep_llm_model_defaults_to_sonnet_5() -> None:
    settings = Settings(_env_file=None)
    assert settings.deep_llm_model == "claude-sonnet-5"


def test_deep_llm_model_is_overridable_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ATSC_DEEP_LLM_MODEL", "claude-opus-5")
    settings = Settings(_env_file=None)
    assert settings.deep_llm_model == "claude-opus-5"
