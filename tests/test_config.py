from app.config import settings


def test_agent_model_setting_is_a_non_empty_string():
    assert isinstance(settings.agent_model, str)
    assert settings.agent_model


def test_gemini_api_key_setting_is_a_non_empty_string():
    assert isinstance(settings.gemini_api_key, str)
    assert settings.gemini_api_key


def test_log_level_setting_is_a_non_empty_string():
    assert isinstance(settings.log_level, str)
    assert settings.log_level


def test_cloudwatch_log_stream_setting_is_a_non_empty_string():
    assert isinstance(settings.cloudwatch_log_stream, str)
    assert settings.cloudwatch_log_stream


def test_cloudwatch_log_group_setting_is_optional():
    assert settings.cloudwatch_log_group is None or isinstance(settings.cloudwatch_log_group, str)
