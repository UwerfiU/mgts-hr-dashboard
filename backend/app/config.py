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

    # Каталог анкетов/вопросов/метрик (WP1) и политики доступа (WP5)
    catalog_path: str = (BACKEND_DIR / "config" / "catalog.yaml").as_posix()
    permissions_path: str = (BACKEND_DIR / "config" / "permissions.yaml").as_posix()

    # Режим запуска: demo — синтетика без внешних ключей; real — реальные источники
    data_mode: str = "demo"

    # Google Forms (WP4). Секреты вне репозитория.
    google_client_secrets_file: str = ""
    google_token_cache: str = (BACKEND_DIR / "secrets" / "forms_token.json").as_posix()
    sync_interval_sec: int | None = None  # переопределение интервала из sources_forms.yaml

    # LLM (любой OpenAI-совместимый эндпоинт). Без ключа — лексиконный fallback.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout: float = 20.0

    # Длительность программы в месяцах
    program_months: int = 6


settings = Settings()
