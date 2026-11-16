# WP1: Нормализованная модель данных + каталог (B1)

**Зависимости:** WP0 завершён (каркас есть). **Блокирует:** WP2, WP3, WP4, WP5.

## Цель
Заменить временную ORM-модель (`app/db/models.py`) нормализованной моделью по PLAN.md §3
и реализовать каталог анкет/вопросов/метрик, загружаемый из `config/catalog.yaml`.

## Файлы в зоне работы
- `backend/app/db/models.py` — **перезаписать**
- `backend/app/catalog/` — новый модуль: `loader.py` (YAML → БД), `access.py` (доступ для аналитики)
- `backend/config/catalog.yaml` — доработать при необходимости (структура уже задана)
- `backend/tests/test_catalog.py`, `backend/tests/test_models.py`

## Что сделать
1. Сущности (PLAN.md §3): `Questionnaire(role, version)`, `Question(questionnaire_id, key, label, type, scale_min, scale_max)`,
   `Metric(id, role, question_keys[])`, `ComparisonPair(intern_question, mentor_question, direction, rule)`,
   `Intern(opaque_id, alias)`, `Mentor(opaque_id, alias)`,
   `Submission(source, source_key, cycle 1–6, role, about_intern_id NULL-able, submitted_at, file_batch_id NULL-able)`,
   `Answer(submission_id, question_key, score NULL-able, text NULL-able)`,
   `SyncState(connector, last_success_at, last_error)`.
2. Уникальность: `(source, source_key)` у Submission — основа идемпотентности (WP3/WP4).
3. `catalog/loader.py`: чтение `catalog.yaml` → idempotent upsert в БД (по ключам), вызывается из lifespan
   (`app/main.py`, одна строка) и доступен вручную. Ошибки валидации конфига — понятное сообщение с полем.
4. `catalog/access.py`: функции для аналитики — вопросы по роли/анкете, метрика → вопросы,
   шкалы для валидации (WP2), пары сравнения (WP5).
5. Связь «о ком» (`about_intern_id`) — опциональна: отправка без связи хранится и учитывается в агрегатах.

## Вне зоны
Нормализация/валидация значений (WP2), API-маршруты (WP5), сигналы (WP8).

## Критерий готовности (BACKEND.md B1)
- Вопрос можно добавить или переименовать через `catalog.yaml`, не меняя таблицы БД и схему API.
- Ответ без связи со стажёром хранится и учитывается там, где это допустимо.

## Тесты
- Загрузка каталога дважды → без дублей; переименование вопроса в YAML → подхватывается при перезагрузке.
- Submission с `about_intern_id=NULL` сохраняется; Answer со `score=NULL` (пропуск) сохраняется.
- Неизвестный questionnaire у вопроса в YAML → ошибка загрузки с указанием поля.
