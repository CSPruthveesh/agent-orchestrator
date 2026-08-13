from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    Application Configuration Settings loaded from environment variables and .env file.
    """
    # Environment & API metadata
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "Async AI Agent Orchestration Platform"
    API_V1_STR: str = "/api/v1"

    # Redis Connection Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    # SQLite Database Settings
    SQLITE_DB_PATH: str = "orchestrator.db"

    # Gemini & LLM Provider API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gemini-2.5-flash"

    # Sandbox & Safety Execution Limits
    SANDBOX_TIMEOUT_MS: int = 5000
    SANDBOX_MAX_CPU_TIMEOUT_MS: int = 5000
    SANDBOX_MAX_MEMORY_MB: int = 256
    MAX_AGENT_TREE_DEPTH: int = 3
    MAX_WORKERS_PER_SUPERVISOR: int = 5
    DEFAULT_AGENT_BUDGET_USD: float = 1.00

    @property
    def redis_connection_url(self) -> str:
        """
        Returns configured REDIS_URL or constructs URL from REDIS_HOST/PORT/DB.
        """
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
