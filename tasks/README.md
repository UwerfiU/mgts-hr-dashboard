# Задания для субагентов (WP)

Каждое задание — самостоятельная задача с чёткой границей файлов. Общие правила:

- Читаем: `BACKEND.md` (норматив), `PLAN.md` (архитектура и структура).
- Работаем только в перечисленных в задании файлах (+ тесты к ним).
- Критерий готовности — из таблицы BACKEND.md, продублирован в каждом задании.
- После выполнения: `pytest tests/ -q` зелёный, OpenAPI (`/docs`) не сломан.

Порядок запуска (см. также PLAN.md §5):

```
WP1 ✅ → WP2 → ┬→ WP3 (Excel)     ─┐
              ├→ WP4 (Forms)      ─┼→ WP6 (запуск/доки)
              └→ WP5 (API+фикстуры, можно параллельно на фикстурах)
Этап 2: WP7 → WP8 ∥ WP9
```

Статус: **WP0–WP6 ✅ — этап 1 завершён** (модель+каталог, нормализация, импорт Excel, коннектор форм, API /api/v1+аналитика+фикстуры, quickstart+seed) — 59 тестов зелёных, E2E-проверка «seed → uvicorn → 3 маршрута» пройдена. Следующий (после материалов организаторов): **WP7** (реальные источники), затем WP8 ∥ WP9.

| Файл | Задание |
|---|---|
| [WP1-data-model-catalog.md](WP1-data-model-catalog.md) | Нормализованная модель данных + каталог из YAML |
| [WP2-normalization.md](WP2-normalization.md) | Адаптеры источников, валидация, provenance, отчёт |
| [WP3-excel-import.md](WP3-excel-import.md) | CLI импорта Excel (dry-run, идемпотентность, замена партии) |
| [WP4-forms-connector.md](WP4-forms-connector.md) | Google Forms poller + sync state + mock-коннектор |
| [WP5-api-v1.md](WP5-api-v1.md) | `/api/v1/{meta,metrics,feedback}` + аналитика + фикстуры |
| [WP6-launch-docs.md](WP6-launch-docs.md) | README quickstart, seed синтетики, финальная проверка |
| [WP7-real-sources.md](WP7-real-sources.md) | Этап 2: маппинг фактических источников |
| [WP8-signals-methodology.md](WP8-signals-methodology.md) | Этап 2: методика сравнения и сигналы с причинами |
| [WP9-ai-module.md](WP9-ai-module.md) | Этап 2: AI-анализ комментариев (темы, сводки, риск) |
