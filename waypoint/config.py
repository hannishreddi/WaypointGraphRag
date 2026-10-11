"""Settings loaded from the environment / .env. Names match .env exactly."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "zenvora_kb"
DEFAULT_AS_OF = date(2026, 10, 10)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr
    llm_provider: Literal["gemini", "anthropic"] = "gemini"
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    model_fast: str  # router and judge
    model_answer: str  # answers (S1, S3, S5)
    llm_rpm: float = 5.0  # client-side requests/min per model; halved on each per-minute 429
    llm_timeout_s: float = 300.0
    gemini_thinking_level: str = "minimal"  # thinkingConfig.thinkingLevel; "" sends none
    cohere_api_key: SecretStr | None = None
    cohere_embed_model: str = "embed-v5.0-fast"
    embed_dim: int = 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
