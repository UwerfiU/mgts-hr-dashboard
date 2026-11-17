# Код-ревью бэкенда MGTS HR Dashboard

> **Статус:** дефекты ниже исправлены в этом же коммите; отчёт сохранён как
> исторический артефакт ревью. Номера строк относятся к коммиту `d9286b1`.
> После исправлений: **86 тестов зелёных**, включая регрессии на реальный Forms API,
> `opaque_id`, ключи Excel, NaN и независимость тестов от порядка запуска.

**Дата:** 2026-11-17
**Ветка:** `backend`, коммит `d9286b1` («step 1»)
**Объём:** ~2 600 строк `backend/app/`, ~1 080 строк тестов, 238 строк YAML-конфигов, 141 файл.
**Статус:** код не изменялся; ревью и воспроизведение дефектов выполнялись во временном окружении `/tmp`.

---

## Содержание

1. [Как проверялось](#1-как-проверялось)
2. [Документы и задания](#2-документы-и-задания)
3. [Что сделано хорошо](#3-что-сделано-хорошо)
4. [Критические дефекты (P0)](#4-критические-дефекты-p0)
5. [Серьёзные проблемы (P1)](#5-серьёзные-проблемы-p1)
6. [Мелочи и гигиена (P2)](#6-мелочи-и-гигиена-p2)
7. [Соответствие критериям BACKEND.md](#7-соответствие-критериям-backendmd)
8. [Приоритетный план исправлений](#8-приоритетный-план-исправлений)

---

## 1. Как проверялось

- Прочитаны все файлы репозитория: документы (`BACKEND.md`, `PLAN.md`, `README.md`, `tasks/WP1…WP9`), код, YAML-конфиги, фикстуры, тесты.
- Собрано изолированное окружение в `/tmp/mgts-venv`:
  - Python 3.14.10
  - fastapi 0.163.1
  - SQLAlchemy 2.1.9
  - google-auth-oauthlib 1.5.0
- Прогнаны тесты:
  - штатный порядок: **59 passed**;
  - изменённый порядок (`tests/test_seed.py` перед `tests/test_api_v1.py`): **7 failed, 10 passed**.
- Подозрительные места воспроизведены отдельными скриптами (`/tmp/probe*.py`), результаты приведены в разделах ниже.
- Проверена загрузка всех модулей пакета (`pkgutil.walk_packages`), генерация OpenAPI, запуск CLI и seed.
- `git status` после проверки чистый: файлы репозитория не модифицировались.

---

## 2. Документы и задания

| Файл | Содержание | Замечания |
|---|---|---|
| `BACKEND.md` | Нормативный контракт: источники, поток данных, задачи B1–B9, критерии готовности | Контракт внятный. Но `internId`/`mentorId` описаны как «непрозрачные стабильные коды», а откуда фронтенд их получает — не сказано; в `/meta` их нет |
| `PLAN.md` | Архитектура, целевая структура, модель данных, работы WP0–WP9 | §6 требует сохранить `signals.py` «как основу WP8» — фактически модуль нерабочий |
| `README.md` | Quickstart, режимы, структура, конфигурация | Команды даны в Windows-варианте без явного указания Linux/macOS; версия Python не указана |
| `tasks/WP1…WP9` | Брифы с границей файлов и критериями готовности | WP3 требует команду `python -m app.sources.excel_importer` — её нет; WP4 требует тесты на `httpx.MockTransport` — их нет |
| `tasks/README.md` | Статус работ | «WP0–WP6 ✅, 59 тестов зелёных» — по тестам верно, по критериям B1–B6 есть оговорки (см. §7) |

Отдельно стоит отметить расхождение документации и кода:

- `tasks/WP3-excel-import.md:14` и docstring `backend/app/sources/excel_importer/cli.py:4` описывают несуществующую точку входа `python -m app.sources.excel_importer`.
- `tasks/WP4-forms-connector.md:42` требует мок HTTP-клиента через `httpx.MockTransport`; фактически тесты используют самописный `MockFormsClient` и вымышленный формат ответа.
- `tasks/README.md:19` заявляет «E2E-проверка seed → uvicorn → 3 маршрута»; в репозитории нет ни скрипта, ни теста, который это воспроизводит.
- `README.md:112-115` обещает «50+ тестов»; фактически 59.

---

## 3. Что сделано хорошо

- Чёткое разделение слоёв: `sources → normalization → db → analytics → api`; API не содержит расчётной логики, а вызывает `app/analytics`.
- Идемпотентность через `UNIQUE(source, source_key)` и upsert — работает (проверено тестами Excel, форм, seed).
- Принцип «пропуск оценки — не ноль» соблюдён сквозняком: `Answer.score` nullable, пустая оценка → `AnswerValue(score=None)`, в `/metrics` пустой месяц → `value: null`.
- Провенанс записи: `source`, `source_key`, `file_batch_id`, `submitted_at`.
- Отчёт нормализации с причинами отклонения строк (`NormalizationReport`, `summary_text()`).
- Разделение прав: персональные срезы, числовая история и тексты — отдельные флаги; «пусто» (200 + `texts: []`) и «запрещено» (403 + `code`) различаются.
- Каталог из YAML без миграций БД; добавление и переименование вопроса работают (тесты `test_catalog.py`).
- 59 тестов действительно проходят в штатном порядке выполнения.

---

## 4. Критические дефекты (P0)

### 4.1. Коннектор Google Forms несовместим с реальным Forms API

**Файл:** `backend/app/sources/forms_poller/poller.py:43-74`

Код написан под вымышленную структуру ответа. Реальный `FormResponse` (по документации Google Forms API) выглядит так:

```json
{
  "formId": "FORM_ID",
  "responseId": "RESPONSE_ID",
  "createTime": "2026-05-01T10:00:00Z",
  "answers": {
    "QUESTION_ID": {
      "questionId": "QUESTION_ID",
      "textAnswers": { "answers": [{ "value": "4" }] }
    }
  }
}
```

Что ожидает код:

| Строка | Код | Реальность | Последствие |
|---|---|---|---|
| `poller.py:51` | `resp.get("name", "")` | поля `name` нет, есть `responseId` | `resp_id = "unknown"` у всех ответов → все записи получают `source_key = form:unknown`, каждый новый ответ перезаписывает предыдущий (тихая потеря данных) |
| `poller.py:55` | `resp.get("answers", [])` | `answers` — это map (объект), а не список | итерация даёт строки-ключи → `'str' object has no attribute 'get'` → синхронизация формы падает |
| `poller.py:60` | `selectedAnswers[].answer` | `textAnswers.answers[].value` | ответы не читаются |
| `poller.py:23-31` | `textQuestionId`, `multipleChoiceQuestion` и т.п. | таких полей нет; есть `questionId` (и `choiceQuestion` вместо `multipleChoiceQuestion`) | маппинг `question_map` по ID вопроса не сработает никогда |

**Воспроизведение:**

```python
real_resp = {
  "responseId": "RID1",
  "createTime": "2026-05-01T10:00:00Z",
  "answers": {
    "Q_CYCLE": {"questionId": "Q_CYCLE", "textAnswers": {"answers": [{"value": "2"}]}},
    "Q_SKILL": {"questionId": "Q_SKILL", "textAnswers": {"answers": [{"value": "4"}]}},
  },
}
response_to_raw(entry, real_resp)
# -> AttributeError: 'str' object has no attribute 'get'
```

Почему не поймано тестами: `tests/test_forms_poller.py:16-26` сам конструирует ответы в выдуманном формате (`textQuestionId`, `selectedAnswers`, `name`) и использует `MockFormsClient`, а не `httpx.MockTransport`, как требовал WP4. WP4 закрыт только для мока.

---

### 4.2. Ключ строки Excel может схлопнуть весь файл в одну запись

**Файл:** `backend/app/sources/excel_importer/reader.py:21-41`

Если `record_key` не задан (или задан с опечаткой), тип по умолчанию — `file_row_hash`, а список `columns` пустой. Тогда у всех строк файла одинаковый ключ `file_hash:da39a3ee5e6b`.

**Воспроизведение:** файл из трёх строк, `record_key` отсутствует:

```
report: accepted=3 created=1 updated=2 skipped=0
rows in DB: 1
['507612f7d4bde304:da39a3ee5e6b']
```

Отчёт рапортует «принято 3», хотя в БД одна запись. То же происходит при опечатке в имени колонки в `columns`: `payload.get(...)` вернёт пустую строку для всех строк.

Для WP7 (реальные конфиги организаторов) это прямой риск тихой потери данных.

---

### 4.3. Персональные срезы используют PK вместо `opaque_id`

**Файлы:**
- `backend/app/api/v1/metrics.py:19-22`
- `backend/app/api/v1/feedback.py:42-45`
- `backend/app/api/v1/meta.py:43-48`
- `backend/app/db/models.py:94` (`Intern.opaque_id`)

```python
def _resolve_person(db: Session, kind: str, opaque_id: str) -> int | None:
    model = Intern if kind == "intern" else Mentor
    row = db.get(model, int(opaque_id)) if str(opaque_id).isdigit() else None
    return row.id if row else None
```

`internId` трактуется как внутренний `Intern.id`, хотя контракт требует непрозрачный стабильный код. При этом `/api/v1/meta` отдаёт только псевдонимы (`aliases.interns` — список строк), без ID, поэтому фронтенд физически не может получить валидный `internId`.

**Воспроизведение** (политика персональных срезов разрешена):

```
intern pk/opaque: 1 AUTO-ec1868c5
metrics by pk      -> 200
metrics by opaque  -> 404 {"code": "METRIC_NOT_FOUND"}
```

Дополнительные проблемы:

- «Человек не найден» отдаётся кодом `METRIC_NOT_FOUND` (`metrics.py:47-53`) — семантически неверно.
- В `/feedback` неизвестный ID даёт `200 {"texts": []}` вместо 404 — несогласовано с `/metrics`.
- Тесты закрепляют неверное поведение: `test_api_v1.py:130,138,163` передают `str(ids["anna"])`, то есть PK.

---

### 4.4. Документированная команда импорта Excel не работает

**Файлы:** `backend/app/sources/excel_importer/` (нет `__main__.py`), `tasks/WP3-excel-import.md:14`, `cli.py:4`

Команда из задания и docstring:

```bash
python -m app.sources.excel_importer --config config/sources_excel.yaml
```

Фактический результат:

```
No module named app.sources.excel_importer.__main__;
'app.sources.excel_importer' is a package and cannot be directly executed
```

Работает только `python -m app.sources.excel_importer.cli`, чего в документации нет. Тесты вызывают `cli_main()` напрямую, поэтому дефект не виден.

---

### 4.5. Настройка OAuth падает на актуальной библиотеке

**Файл:** `backend/app/sources/forms_poller/setup_oauth.py:38`

```python
creds = flow.run_console()
```

В `google-auth-oauthlib` 1.5.0 (ставится по `requirements.txt`, ограничение `>=1.2`) метода больше нет:

```
version 1.5.0
run_console: False
run_local_server: True
```

Первичная настройка доступа к формам по инструкции невозможна — `AttributeError`. Нужен `run_local_server()` либо верхняя граница версии.

Отдельно: `client.py:49` и `setup_oauth.py:41` записывают токен (включая refresh token) через `write_text` без ограничения прав — обычно получается `0644`. Нужен `chmod 600`.

---

### 4.6. `analytics/signals.py` не импортируется

**Файл:** `backend/app/analytics/signals.py:24-25`

```python
from ..db.models import CommentInsight, Response, Signal, Trainee
from .survey_schema import PAIRED_QUESTIONS, label
```

После WP1 этих моделей и модуля `survey_schema` не существует. Проверка импорта всех модулей пакета:

```
modules with import errors:
  ('app.analytics.signals', 'ImportError',
   "cannot import name 'CommentInsight' from 'app.db.models'")
```

Сейчас модуль не подключён к API, но он мёртвый и сломает любой импорт-скан. WP8 планировалось делать «на его основе» (`PLAN.md` §6).

---

## 5. Серьёзные проблемы (P1)

### 5.1. Тесты зависят от порядка запуска

**Файлы:** `tests/conftest.py:24-32`, `tests/test_api_v1.py:5-6,104-115,199-200`, `tests/test_seed.py`

Фикстура `db` не загружает каталог — это делает только `catalog_db` или `client` (через lifespan). Если запустить `tests/test_seed.py` первым:

```
FAILED tests/test_seed.py::test_seed_counters            - assert 0 == 30
FAILED tests/test_seed.py::test_seed_idempotent          - assert 0 == 60
FAILED tests/test_seed.py::test_seed_reset               - assert 0 == 60
FAILED tests/test_seed.py::test_seed_skipped_score_is_null
FAILED tests/test_seed.py::test_seed_links_intern_and_mentor
FAILED tests/test_api_v1.py::test_metrics_global_empty_month
FAILED tests/test_api_v1.py::test_feedback_allowed
7 failed, 10 passed
```

Причины:

- `test_seed_*`: каталог пуст, `normalize_record` отбрасывает все записи с причиной «анкета не найдена», счётчики 0 вместо 30/60.
- `test_metrics_global_empty_month` и `test_feedback_allowed`: seed записал циклы 1–6, а тесты предполагают, что месяц 6 «гарантированно пуст».

Тесты сломаются также при `pytest-xdist`, случайном порядке (`pytest-randomly`) или запуске отдельных файлов. Часть проверок держится на неявном порядке выполнения.

### 5.2. Неполная валидация каталога и нормализации

**Файл:** `backend/app/catalog/loader.py`

- `:96-111` — не проверяется, что `metric.role` соответствует роли анкеты вопросов из `question_keys`. Метрика `intern` может ссылаться на вопрос наставника — аналитика молча вернёт пустую серию.
- `:120-135` — не проверяются `direction` и `rule` у `comparison_pairs`. В `analytics/comparison.py:56` любое значение, кроме `intern_minus_mentor`, трактуется как обратное направление.
- Нет проверки `version > 0`.

**Файл:** `backend/app/normalization/core.py:73-82` — не проверяется, что `spec.role` совпадает с ролью анкеты.

**Воспроизведение:**

```
role mismatch: reasons: [] role: mentor qid: intern_v1
```

### 5.3. Excel: отсутствующая колонка превращается в тихий NULL

Если в `field_map` опечатка в имени колонки, значения нет → это трактуется как «пустая оценка» → `score=NULL`, запись принимается, в отчёте ни слова.

**Воспроизведение:** конфиг содержит `score_typo: task_clarity`, колонки `score_typo` в файле нет:

```
accepted: 2 skipped: []
```

Дополнительно `reader.py:57` при дублирующихся заголовках молча оставляет последний столбец:

```
payload: {'trainee_name': 'Анна', 'month': 1, 'score_skill': 2}   # в файле было 4 и 2
```

### 5.4. `--replace-batch` удаляет данные до импорта

**Файл:** `backend/app/sources/excel_importer/cli.py:72-75`

Удаление старой партии выполняется до чтения и валидации нового файла. Если новый файл битый, не найден лист или импорт упадёт — старая партия уже удалена.

Дополнительно `cli.py:137` передаёт `--replace-batch` в каждый файл цикла, поэтому при импорте нескольких файлов можно удалить партию другого файла.

### 5.5. Код выхода CLI не сигнализирует о полностью пропущенном файле

**Файлы:** `backend/app/normalization/report.py:27-29`, `cli.py:140`

`NormalizationReport.ok` учитывает только `errors`, но не `skipped`. Файл, в котором 100 % строк отклонено (например, неверный `questionnaire` в конфиге), завершается с кодом 0.

### 5.6. Валидация значений: NaN и число в текстовом поле

**Файл:** `backend/app/normalization/core.py:96-108`

- `float("nan")` проходит проверку шкалы: сравнения с NaN ложны. SQLite сохраняет NaN как NULL → тихая потеря оценки.

  ```
  reasons: [] score: nan
  # затем в /metrics: value=null, n=0
  ```

- Число в текстовом поле принимается как текст (`"5"`). WP2 требовал отбраковывать «текст в поле оценки и наоборот»; обратное направление не проверяется.

### 5.7. Фильтр по наставнику не работает для Excel-данных

**Файлы:** `backend/app/sources/excel_importer/cli.py:44-54`, `backend/config/sources_excel.yaml`, `backend/app/analytics/common.py:14-22`

`SourceSpec` умеет `author_mentor_field`, но Excel-адаптер его не заполняет, и в конфиге такого поля нет. Excel-строки наставников получают `about_intern_id`, но `author_mentor_id = NULL`.

`linked_intern_ids()` строит связи только по `author_mentor_id`, поэтому `/metrics?mentorId=...` для импортированной истории всегда даёт пустой результат, хотя связи «наставник → стажёр» в данных есть.

### 5.8. Права на тексты зависят от права на числовую историю

**Файл:** `backend/app/api/v1/feedback.py:37-39`

Персональный фильтр текстов требует одновременно `personal_slices_allowed` **и** `numeric_history_allowed`. `BACKEND.md` прямо говорит, что числовую историю и тексты надо проверять отдельно. При `text_display_allowed: true` и `numeric_history_allowed: false` запрос `/api/v1/feedback?internId=...` возвращает 403 (проверено).

### 5.9. Прочие серьёзные проблемы

| Проблема | Где | Детали |
|---|---|---|
| Второй персональный фильтр молча игнорируется | `metrics.py:43-53` | При одновременной передаче `internId` и `mentorId` фильтр по наставнику не применяется, ответ 200 |
| `_score_by_intern` — «последний победил» | `analytics/comparison.py:25-33` | Если о стажёре за месяц ответили два наставника, в расчёт попадает произвольное значение (проверено: `{1: 1.0}`) |
| Кривой `form_id` ломает весь проход poller | `main.py:41`, `poller.py:109` | `form_id: null` → `AttributeError` в `_build_forms_poller`; отсутствие ключа → `KeyError` вне `try` в `sync_once` |
| Нет Pydantic-моделей ответов | `api/v1/*` | `app.openapi()` содержит только `HTTPValidationError` и `ValidationError`; схем `/meta`, `/metrics`, `/feedback` нет, генерация клиента для фронта невозможна |
| Токен OAuth пишется с правами по umask | `client.py:49`, `setup_oauth.py:41` | Обычно `0644`, хотя содержит refresh token |
| Фикстура не соответствует API | `fixtures/metrics/comparison_unavailable.json` | Для `motivation` указан `status: "unavailable"` и линия наставника, но у метрики нет пары → API вернёт `not_configured` и одну серию |
| `seed --reset` не очищает участников | `scripts/seed_demo.py:127-130` | Удаляются только `Submission`; `Intern`/`Mentor` остаются (проверено: 7 → 7) |
| `source="demo"` вне описанного enum | `scripts/seed_demo.py:108` | Модель и документация описывают `excel|form` |
| Ошибки приложения и валидации FastAPI разного формата | `api/v1/codes.py` | `bad_request` → `422 {code, message}`, а `Query(ge=...)` → `422 {detail: [...]}`; фронту нужно обрабатывать два формата |
| `expected_per_cycle` пропускает `bool` | `policy.py:69` | `isinstance(True, int)` → `true` в YAML превращается в 1 |

---

## 6. Мелочи и гигиена (P2)

- `app/main.py:6` — устаревший docstring «Дальше: WP5».
- `meta.py:65` — `lastSuccessAt` без таймзоны (`2026-11-17T07:26:52.394754`): SQLite не хранит offset, фронт может принять UTC за локальное время.
- `.gitignore` не исключает `*.xlsx` — реальные файлы с персональными данными можно случайно закоммитить (WP7 это запрещает).
- В корне репозитория лежит `photo_2026-11-16_20-57-34.jpg` (361 КБ) — посторонний бинарь.
- `README.md`: команды только для Windows (`Scripts/`), версия Python не указана.
- Код требует Python ≥ 3.10 (`int | None`), а `datetime.fromisoformat` с суффиксом `Z` — ≥ 3.11. На 3.10 `normalization/core.py:130` молча потеряет дату.
- `requirements.txt`: `pytest` в прод-зависимостях; основные пакеты без верхних границ (уже привело к поломке `run_console` в google-auth-oauthlib 1.5).
- `analytics/series.py` — N+1 запросов (по одному на месяц) плюс ленивая загрузка `answers`.
- SQLite: `PRAGMA foreign_keys` не включается, FK из `models.py` фактически не проверяются.
- `excel_importer/cli.py`: `--dry-run` всё равно вызывает `load_catalog(db)` и коммитит каталог — «без записи» верно только для данных.
- `excel_importer/cli.py:115-117` резолвит пути от текущего каталога, тогда как документация говорит «пути относительно `backend/`».
- CORS `allow_origins=["*"]` — допустимо для прототипа, но стоит зафиксировать как осознанное решение.
- Нет `pyproject.toml`, линтера, CI; нет тестов на реальный парсинг Forms API, `opaque_id`, CLI-точку входа, отсутствующие колонки Excel, роли в каталоге.
- Неиспользуемые импорты: `tests/test_normalization.py:7` (`Answer`), `tests/test_api_v1.py:13` (`Submission`) и др.
- `analytics/signals.py` продублирован комментарием-заголовком «STAGE 2 / WP8 — основа из начального скелета. Не подключена к API» — но это не спасает от ImportError.
- `data/.gitkeep` — ок; `backend/secrets/` отсутствует и создаётся при OAuth (в `.gitignore` есть).

---

## 7. Соответствие критериям BACKEND.md

| Критерий | Статус | Комментарий |
|---|---|---|
| **B1.** Вопрос добавляется/переименовывается через конфиг; ответ без связи хранится | ✅ | Проверено `test_catalog.py`, `test_models.py` |
| **B2.** Два формата → один тип; отклонённые строки с причиной; пропуск ≠ 0 | ⚠️ | Основное работает; NaN, число в текстовом поле, несоответствие роли и анкеты не проверяются |
| **B3.** Отчёт принято/пропущено/ошибки; повтор не дублирует | ⚠️ | В штатном конфиге работает; ключ по умолчанию схлопывает строки, документированная CLI-команда не запускается |
| **B4.** Новый ответ в API в пределах интервала; без дублей; ошибка + время успеха | ❌ для real | Мок-путь работает; реальный Forms API не разбирается |
| **B5.** Фильтры, «пусто» ≠ «запрещено», ограничения на сервере | ⚠️ | Состояния различаются; персональные срезы фактически недоступны из-за PK вместо `opaque_id` |
| **B6.** Запуск по инструкции, без ключей, секреты вне репозитория | ✅/⚠️ | Demo запускается; инструкция неполная (Python, Linux, CLI) |
| **B7–B9** (этап 2) | — | Не реализованы; `signals.py` нерабочий, AI-модуль не подключён к API |

---

## 8. Приоритетный план исправлений

1. **Forms-парсер** (`poller.py:43-74`): использовать `responseId`, `answers` как map, `questionId`, `textAnswers.answers[].value`; добавить тест на реальный JSON и `httpx.MockTransport`.
2. **Ключ строки Excel** (`reader.py:21-41`): валидировать непустой `columns` и существование колонок; без ключа — ошибка конфигурации, а не «одна запись на файл».
3. **Идентификаторы** (`metrics.py:19-22`, `feedback.py:42-45`, `meta.py`): искать по `opaque_id`, отдавать в `/meta` пары `{id, alias}`, добавить код `PERSON_NOT_FOUND`; привести тесты к новому поведению.
4. **CLI**: добавить `app/sources/excel_importer/__main__.py` либо исправить документацию на `...cli`.
5. **OAuth**: `run_local_server()`; `chmod 600` для файла токена.
6. **`signals.py`**: удалить или привести импорты к `Submission/Answer` — иначе WP8 начнётся с поломки.
7. **Тесты**: загружать каталог в фикстуре `db`; убрать зависимость от «месяц 6 пуст»; изолировать данные по `source_key`/БД.
8. **Валидация каталога**: роль метрики ↔ роль вопросов, `direction`/`rule`, `spec.role` ↔ `questionnaire.role`.
9. **Отчёт и CLI**: `ok` должен учитывать `skipped`; `--replace-batch` — только после успешной валидации.
10. **Контракт**: Pydantic-схемы ответов; привести фикстуры к реальному поведению API.
11. **Excel**: сообщать об отсутствующих колонках и дублях заголовков; не превращать опечатку в NULL.
12. **Права**: отвязать персональный фильтр текстов от `numeric_history_allowed`.
13. **Гигиена**: `.gitignore` для `*.xlsx`, убрать посторонний jpg, указать версию Python и Linux-команды, закрепить версии зависимостей.

---

*Отчёт подготовлен без изменения файлов репозитория. Все эксперименты выполнялись во временном окружении `/tmp`.*
