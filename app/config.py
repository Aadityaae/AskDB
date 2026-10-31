from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = ''
    readonly_database_url: str = ''
    workspace_url: str = ''
    llm_provider: Literal['groq', 'ollama'] = 'groq'
    groq_api_key: SecretStr = SecretStr('')
    groq_model: str = 'openai/gpt-oss-120b'
    ollama_base_url: str = 'http://localhost:11434'
    ollama_model: str = 'qwen3:8b'
    embedding_model: str = 'all-MiniLM-L6-v2'
    dataset_dir: str = '~/.cache/texttosql/datasets'
    speech_model: str = 'tiny.en'
    speech_model_dir: str = '~/.cache/texttosql/speech'
    max_result_rows: int = Field(1000, ge=1, le=10000)
    max_estimated_rows: int = Field(1000000, ge=1)
    max_estimated_cost: float = Field(100000, gt=0)
    max_query_seconds: int = Field(10, ge=1, le=120)
    max_subquery_depth: int = Field(3, ge=0, le=10)
    validation_mode: Literal['strict', 'balanced', 'fast'] = 'strict'


@lru_cache
def settings() -> Settings:
    return Settings()
