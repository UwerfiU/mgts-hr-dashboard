"""Точка входа FastAPI-приложения.

Состояние:
  * WP1 — каталог из config/catalog.yaml при старте;
  * WP4 — poller Google Forms (режим real + настроенный OAuth); в demo не стартует;
  * WP5 — маршруты /api/v1/{meta,metrics,feedback}.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import feedback as v1_feedback
from .api.v1 import meta as v1_meta
from .api.v1 import metrics as v1_metrics
from .catalog.loader import load_catalog
from .config import settings
from .db.database import SessionLocal, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mgts")


def _build_forms_poller():
    """Poller для режима real; None — если не настроен (demo или нет ключей)."""
    if settings.data_mode != "real":
        logger.info("Forms poller отключён: data_mode=%s", settings.data_mode)
        return None
    if not settings.google_client_secrets_file and not Path(settings.google_token_cache).exists():
        logger.info("Forms poller отключён: нет OAuth-токена (python -m app.sources.forms_poller.setup_oauth)")
        return None

    from .sources.forms_poller.client import FormsClient
    from .sources.forms_poller.poller import FormsPoller

    cfg_path = Path(settings.catalog_path).parent / "sources_forms.yaml"
    if not cfg_path.exists():
        logger.info("Forms poller отключён: конфиг %s не найден", cfg_path)
        return None
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    forms = []
    for entry in cfg.get("forms", []):
        form_id = entry.get("form_id")
        # Пустой/None/TODO form_id раньше ронял приложение на .startswith()
        if not isinstance(form_id, str) or not form_id.strip() or form_id.startswith("TODO"):
            continue
        missing = [k for k in ("role", "questionnaire", "cycle_field") if not entry.get(k)]
        if missing:
            logger.warning("Forms poller: форма %s пропущена — не заданы %s", form_id, ", ".join(missing))
            continue
        forms.append(entry)
    if not forms:
        logger.info("Forms poller отключён: в %s нет заполненных form_id", cfg_path)
        return None

    client = FormsClient(
        client_secrets_file=settings.google_client_secrets_file,
        token_path=settings.google_token_cache,
    )
    interval = settings.sync_interval_sec or (cfg.get("sync") or {}).get("interval_seconds", 120)
    return FormsPoller(client=client, entries=forms, interval_seconds=interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        load_catalog(db)  # невалидный конфиг каталога → fail fast со списком ошибок
    finally:
        db.close()

    poller = _build_forms_poller()
    if poller is not None:
        poller.start()
        logger.info("Forms poller запущен (интервал %d c)", poller.interval_seconds)
    yield
    if poller is not None:
        poller.stop()


app = FastAPI(
    title="MGTS HR Dashboard API",
    version="0.1.0",
    description=(
        "Бэкенд аналитического дашборда шестимесячной программы стажировок МГТС: "
        "интеграция с источниками (Excel, Google Forms), нормализация, аналитика, API для дашборда HR."
    ),
    lifespan=lifespan,
)

# Фронтенд живёт отдельно — разрешаем запросы с любого origins (прототип).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


for r in (v1_meta.router, v1_metrics.router, v1_feedback.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
