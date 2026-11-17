# MGTS HR Dashboard — бэкенд

Бэкенд интеллектуального аналитического дашборда шестимесячной программы стажировок МГТС:
источники (два Excel + Google Forms), нормализация, аналитика оценок, а на этапе 2 —
сигналы и AI-анализ комментариев для HR.

## Документы

| Файл | Что это |
|---|---|
| [BACKEND.md](BACKEND.md) | **Нормативный контракт** с фронтендом: источники, поток данных, задачи B1–B9, критерии готовности |
| [PLAN.md](PLAN.md) | Общий план: архитектура, структура репозитория, модель данных, работы WP0–WP9 |
| [tasks/](tasks/) | Детальные задания по каждому WP (брифы с границей файлов и критериями) |

## Быстрый старт

Проект запускается **без интернета и внешних ключей** — в режиме `demo` на синтетических данных.
Требуется **Python 3.11+** (используется `datetime.fromisoformat` с суффиксом `Z`).

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
# для тестов: .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                             # по умолчанию — режим demo

# 1) сгенерировать синтетическую БД (5 стажёров × 5 наставников, циклы 1–6):
.venv/bin/python -m app.scripts.seed_demo        # повторный запуск не создаёт дублей; --reset — очистить демо-данные

# 2) поднять сервис:
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Windows: замените `.venv/bin/python` на `.venv\Scripts\python`, `.venv/bin/pip` на `.venv\Scripts\pip`.

Импорт исторических Excel (из `backend/`, пути в конфиге — относительно `backend/`):

```bash
.venv/bin/python -m app.sources.excel_importer --config config/sources_excel.yaml --dry-run
.venv/bin/python -m app.sources.excel_importer --config config/sources_excel.yaml
```

Проверка:

- `http://127.0.0.1:8000/docs` — Swagger по API;
- `GET /health` — живость;
- `GET /api/v1/meta` — справочники, режим, права, статус синхронизации;
- `GET /api/v1/metrics?metricId=motivation` — охват/динамика/распределение/сравнение;
- `GET /api/v1/feedback` — комментарии (в demo показаны).

Тесты: `.venv/bin/python -m pytest tests/ -q` (Windows: `.venv\Scripts\python -m pytest tests/ -q`).

### Что в демо-«сюжете» (для проверки глазами)

- **Демо Глеб** — стабильно слабые мотивация и удовлетворённость, низкая поддержка наставника;
  негативные комментарии в циклах 5–6 (вход для AI-анализа этапа 2);
- **Демо Вера** — расхождение самооценки и оценки наставника по росту навыков
  (`/api/v1/metrics?metricId=skill_growth`: блок `comparison` показывает устойчивый зазор);
- **Демо Дарья** в цикле 1 пропустила оценку — она хранится как `NULL`, а не `0`.

## API (контракт для фронтенда)

Три маршрута + `/health`; полный контракт и примеры ответов — в [BACKEND.md](BACKEND.md),
статические фикстуры — в [`backend/fixtures/`](backend/fixtures/) (все состояния: «пусто» ≠ «запрещено»).

| Маршрут | Назначение |
|---|---|
| `GET /api/v1/meta` | циклы, каталог метрик по ролям со шкалами, категории комментариев, флаги детализации, dataMode, статус синхронизации |
| `GET /api/v1/metrics?metricId&fromMonth&toMonth[&internId\|mentorId]` | охват, динамика по циклам (`null` — нет данных), распределение, сравнение стажёр↔наставник для настроенных пар |
| `GET /api/v1/feedback?fromMonth&toMonth[&role\|categoryId\|internId]` | разрешённые к показу комментарии; при запрете — `403 + code`, а не пустой список |

## Режимы и источники

- **demo** (по умолчанию): сервис работает на сохранённой БД; poller форм не стартует,
  отсутствие интернета/ключей не мешает. Тексты синтетики в `/feedback` показаны автоматически.
- **real**: `MGTS_DATA_MODE=real` в `.env`. Тогда:
  - история импортируется CLI из двух Excel (см. `config/sources_excel.yaml`, бриф [WP3](tasks/WP3-excel-import.md));
  - новые ответы приходят опросом Google Forms (polling, без публичного webhook) — подключение по
    [чеклисту WP4](tasks/WP4-forms-connector.md): OAuth-секреты кладутся в `backend/secrets/`
    (вне репозитория), разовая настройка: `.venv/bin/python -m app.sources.forms_poller.setup_oauth`,
    `formId` и маппинг вопросов — в `config/sources_forms.yaml`.

Сбой внешней синхронизации не стирает историю: время последней успешной синхронизации и ошибка
хранятся в `SyncState` и видны в `/api/v1/meta → sync`.

## Конфигурация

| Файл | Что настраивается |
|---|---|
| `backend/config/catalog.yaml` | **единственное** место с анкетами, вопросами, метриками и парами сравнения; добавление/переименование вопроса не требует миграций БД и не меняет схему API |
| `backend/config/sources_excel.yaml` | пути к двум историческим Excel и маппинг колонок → вопросы |
| `backend/config/sources_forms.yaml` | formId, интервал опроса, маппинг полей форм → вопросы |
| `backend/config/permissions.yaml` | права на детализацию (персональные срезы, числовая история, тексты) и план ответов на цикл для coverage |
| `backend/.env.example` | переменные окружения (`MGTS_*`): режим, БД, OAuth-путь, LLM (этап 2) |

Секреты (OAuth Google, LLM-ключи) и реальные данные хранятся **вне репозитория**
(`.gitignore` покрывает `.env`, `backend/secrets/`, `backend/data/*.db`, `backend/data/*.xlsx`, `backend/data/*.xls`).

## Структура

```
backend/
├── app/
│   ├── main.py              # FastAPI: lifespan (БД + каталог), роутеры /api/v1, /health
│   ├── config.py            # настройки (MGTS_*)
│   ├── catalog/             # каталог из YAML: загрузка/валидация/доступ
│   ├── db/                  # модели (нормализованная схема) и сессии
│   ├── normalization/       # общий слой: спецификация источника, валидация, provenance, отчёт
│   ├── sources/
│   │   ├── excel_importer/  # CLI-импорт истории из Excel (dry-run, идемпотентность)
│   │   └── forms_poller/    # Google Forms polling + SyncState + mock для офлайн
│   ├── analytics/           # расчёты: coverage / series / distribution / comparison (API их только вызывает)
│   ├── api/v1/              # маршруты /api/v1/{meta,metrics,feedback}
│   ├── policy.py            # права на детализацию из permissions.yaml
│   ├── ai/                  # этап 2: LLM-клиент и анализ комментариев (WP9)
│   └── scripts/seed_demo.py # генерация синтетической БД
├── config/                  # YAML-конфиги (см. таблицу выше)
├── fixtures/                # статические примеры ответов для фронтенда
├── tests/                   # pytest: модель, каталог, нормализация, Excel, формы, API, seed, сигналы
└── data/                    # локальная БД (вне git)
```

## Тесты и гигиена

- `pytest tests/ -q` — полный прогон (модель, каталог, нормализация, Excel, формы, API, seed).
- При изменении схемы БД удалите `backend/data/mgts.db` — прототип работает на `create_all`, без миграций.
- В репозитории нет ключей и реальных данных; примеры настроек доступны команде.
