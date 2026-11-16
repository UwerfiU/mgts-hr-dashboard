# MGTS HR Dashboard — бэкенд

Бэкенд интеллектуального аналитического дашборда шестимесячной программы стажировок МГТС:
интеграция с источниками (два Excel + Google Forms), нормализация, аналитика оценок,
сигналы и AI-анализ комментариев для HR.

## Документы

| Файл | Что это |
|---|---|
| [BACKEND.md](BACKEND.md) | **Нормативный контракт** с фронтендом: источники, поток данных, задачи B1–B9, критерии готовности |
| [PLAN.md](PLAN.md) | Общий план: архитектура, структура репозитория, модель данных, работы WP0–WP9 |
| [tasks/](tasks/) | Детальные задания для субагентов по каждому WP |

## Быстрый старт (каркас, WP0)

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows; Linux/macOS: .venv/bin/pip
cp .env.example .env                             # по умолчанию — режим demo без внешних ключей
.venv/Scripts/python -m uvicorn app.main:app --reload
```

- `GET /health` — живость сервиса (полные маршруты `/api/v1/*` появятся в WP5).
- Тесты: `.venv/Scripts/python -m pytest tests/ -q`.

Секреты (OAuth Google, LLM-ключи) и реальные данные хранятся **вне репозитория**.
