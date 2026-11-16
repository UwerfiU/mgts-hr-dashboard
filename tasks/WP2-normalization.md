# WP2: Общая нормализация (B2)

**Зависимости:** WP1. **Блокирует:** WP3, WP4, WP5.

## Цель
Единый слой «сырой payload источника → каноническая запись» с валидацией, provenance и отчётом об отклонениях.

## Файлы в зоне работы
- `backend/app/sources/base.py` — интерфейс адаптера: `RawRecord(source, source_key, payload)` + контракт `read()`
- `backend/app/normalization/` — `mapper.py` (маппинг по конфигам), `validator.py`, `report.py`
- `backend/config/sources_excel.yaml`, `config/sources_forms.yaml` — секции маппинга (структура задана, доработать при необходимости)
- `backend/tests/test_normalization.py`

## Что сделать
1. Каноническая запись: `{role, cycle, about_intern (nullable), answers: {question_key: score|text}, submitted_at, source, source_key}`.
2. Маппинг строго по конфигам: «столбец Excel / ID вопроса формы → внутренний ключ вопроса». Фронт этих маппингов не знает.
3. Валидация (каждая причина — в отчёте):
   - цикл вне 1–6; неизвестная роль; неизвестный ключ вопроса;
   - оценка вне шкалы вопроса (по каталогу WP1) → строка отклоняется, а не «чинится»;
   - **пустое значение оценки → `score=NULL`, никогда не 0** (критерий B2);
   - текст в поле оценки и наоборот.
4. Provenance: у каждой записи — источник (`excel`/`form`), ключ в источнике, batch id (для Excel).
5. Отчёт: структура `{accepted: n, skipped: [{key, reason}], errors: [{key, reason}]}`; формат для stdout (WP3) и для API-ответов.
6. Функция `normalize_and_store(records, db)` — общий путь записи для WP3/WP4 (upsert по `(source, source_key)`,
   повтор = обновление значений, не дубль).

## Вне зоны
Чтение xlsx (WP3), работа с Forms API (WP4), расчёты (WP5).

## Критерий готовности (BACKEND.md B2)
- Два разных входных формата дают одинаковый тип записи.
- Отклонённые строки видны в отчёте с причиной.
- Пропуск оценки не превращается в ноль.

## Тесты
Table-driven: пустая оценка → NULL; оценка 7 при шкале 1–5 → rejected+reason; цикл 0 и 7 → rejected;
неизвестный вопрос → rejected; одинаковый payload из «excel» и «forms» → идентичная каноническая запись;
повторный `normalize_and_store` с тем же source_key → одна запись.
