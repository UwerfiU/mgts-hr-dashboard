"""Конфигурация приложения. Все настройки можно переопределить через env (префикс MGTS_)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="MGTS_",
        extra="ignore",
    )

    # База данных. По умолчанию SQLite в backend/data/mgts.db
    db_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'mgts.db').as_posix()}"

    # LLM (любой OpenAI-совместимый эндпоинт). Без ключа — лексиконный fallback.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout: float = 20.0

    # Длительность программы в месяцах
    program_months: int = 6


settings = Settings()
