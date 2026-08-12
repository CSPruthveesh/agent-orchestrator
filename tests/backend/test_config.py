import pytest
from src.backend.config import Settings


def test_default_settings_instantiation():
    """
    Test that default settings initialize with correct types and default values.
    """
    s = Settings()
    assert s.ENVIRONMENT == "development"
    assert s.DEBUG is True
    assert s.REDIS_HOST == "localhost"
    assert s.REDIS_PORT == 6379
    assert s.redis_connection_url == "redis://localhost:6379/0"
    assert s.DEFAULT_LLM_MODEL == "gemini-2.5-flash"
    assert s.SANDBOX_MAX_CPU_TIMEOUT_MS == 5000
    assert s.DEFAULT_AGENT_BUDGET_USD == 1.00


def test_gemini_api_key_setting():
    """
    Test setting custom GEMINI_API_KEY.
    """
    s = Settings(GEMINI_API_KEY="test_gemini_key_123")
    assert s.GEMINI_API_KEY == "test_gemini_key_123"


def test_custom_redis_url_override():
    """
    Test that custom REDIS_URL property overrides default host:port assembly.
    """
    s = Settings(REDIS_URL="redis://user:pass@remotehost:6380/2")
    assert s.redis_connection_url == "redis://user:pass@remotehost:6380/2"
