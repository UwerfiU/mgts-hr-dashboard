"""Точка входа FastAPI-приложения.

Состояние (WP0): каркас — init БД + /health.
Дальше:
  * WP4 — запуск poller'а форм в lifespan;
  * WP5 — маршруты /api/v1/{meta,metrics,feedback}.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # WP4: здесь стартует poller форм (старт + интервал)
    yield


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


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
