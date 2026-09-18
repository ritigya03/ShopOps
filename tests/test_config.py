from app.config import settings


def test_agent_model_setting_is_a_non_empty_string():
    assert isinstance(settings.agent_model, str)
    assert settings.agent_model


def test_gemini_api_key_setting_is_a_non_empty_string():
    assert isinstance(settings.gemini_api_key, str)
    assert settings.gemini_api_key
