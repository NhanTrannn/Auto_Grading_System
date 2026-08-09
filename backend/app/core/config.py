from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Autograding2026"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]

    database_url: str = "sqlite:///./autograding.db"

    # LLM credentials, consumed by the wrapped pipeline.py (its own CFG dict
    # reads these same env vars directly — kept here too so FastAPI code that
    # needs them doesn't have to reach into pipeline.CFG).
    llm_api_key: str = ""
    llm_model_name: str = ""
    llm_base_url: str = ""
    llm_model_api: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
