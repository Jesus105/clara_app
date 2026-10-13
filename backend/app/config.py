from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")
    database_url: str = "sqlite:///./clara.db"
    openrouter_api_key: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENROUTERKEY"))
    openrouter_model: str = "google/gemini-2.5-flash-lite"
    llm_max_total_usd: float = Field(default=3, ge=0, le=3)
    demo_password: str = "clara-demo-local"
    session_secret: str = "local-development-secret-change-before-publication"
    cookie_secure: bool = False
    background_worker: bool = True
    seed_demo: bool = True
    allowed_origins: str = "http://localhost:5173,http://localhost:8000"
    frontend_dir: str = "../frontend/dist"


@lru_cache
def settings():
    return Settings()

