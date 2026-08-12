import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings for the Async AI Agent Orchestration Platform.
    Parses environment variables and .env configuration files.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # General App Configuration
    ENVIRONMENT: str = Field(default="development", description="Execution environment")
    DEBUG: bool = Field(default=True, description="Debug mode flag")
    PROJECT_NAME: str = Field(
        default="Async AI Agent Orchestration Platform",
        description="Project title"
    )
    API_V1_STR: str = Field(default="/api/v1", description="REST API v1 prefix")

    # Redis Task Queue & Checkpoint Storage
    REDIS_HOST: str = Field(default="localhost", description="Redis server host")
    REDIS_PORT: int = Field(default=6379, description="Redis server port")
    REDIS_DB: int = Field(default=0, description="Redis database index")
    REDIS_URL: Optional[str] = Field(default=None, description="Full Redis connection URL")

    # SQLite Persistence Configuration
    SQLITE_DB_PATH: str = Field(
        default="orchestrator.db",
        description="SQLite file path for durable execution trace history"
    )

    # LLM API Keys & Model Defaults (Gemini Free Tier Primary)
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API key")
    DEFAULT_LLM_MODEL: str = Field(default="gemini-2.5-flash", description="Default LLM model")

    # C++ Native Execution Sandbox Limits
    SANDBOX_MAX_CPU_TIMEOUT_MS: int = Field(
        default=5000,
        description="Hard execution timeout in milliseconds for native sandbox runner"
    )
    SANDBOX_MAX_MEMORY_MB: int = Field(
        default=256,
        description="Maximum RAM allocation limit in MB for native sandbox runner"
    )

    # Agent Lifecycle & Budget Limits
    MAX_AGENT_TREE_DEPTH: int = Field(
        default=3,
        description="Maximum recursion depth for supervisor -> worker sub-agents"
    )
    MAX_WORKERS_PER_SUPERVISOR: int = Field(
        default=5,
        description="Maximum concurrent worker sub-agents per supervisor"
    )
    DEFAULT_AGENT_BUDGET_USD: float = Field(
        default=1.00,
        description="Default maximum token spend budget per agent execution run"
    )

    @property
    def redis_connection_url(self) -> str:
        """
        Computes the active Redis URL.
        """
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# Instantiated global settings singleton
settings = Settings()
