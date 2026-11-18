# mgts-hr-dashboard

Дашборд шестимесячной программы стажировок МГТС: FastAPI-бэкенд (`backend/`) + React/Vite-фронтенд (`frontend/`).

## Демо: фронт + бэк вместе

Бэкенд в режиме `demo` (синтетические данные, без внешних ключей) и персональными срезами
(отдельный файл прав — дефолтный `config/permissions.yaml`, на который опираются тесты, не меняется):

```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt   # Windows; в Linux/Mac: .venv/bin/python
.venv/Scripts/python -m app.scripts.seed_demo --reset                             # 5 стажёров × 5 наставников, циклы 1–6

MGTS_DATA_MODE=demo \
MGTS_PERMISSIONS_PATH="$(pwd)/config/permissions.demo.yaml" \
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Фронтенд в HTTP-режиме (Vite проксирует `/api` на бэкенд, CORS не нужен):

```bash
cd frontend
npm ci
VITE_DATA_MODE=http API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

Открыть http://127.0.0.1:5173. Без `VITE_DATA_MODE=http` фронт работает на встроенных моках (режим по умолчанию).

Контракт бэкенда и контракта дашборда различаются — согласование формы ответов делает адаптер
`frontend/src/data/adapter.ts` (см. также README в `frontend/`).

## Сюжеты демо (seed)

* «Демо Глеб» — стабильно слабые мотивация/удовлетворённость, низкая поддержка наставника, негативные комментарии в циклах 5–6;
* «Демо Вера» — расхождение самооценки и оценки наставника по росту навыков (цикл 3+): блок сравнения показывает устойчивый зазор;
* «Демо Дарья» — пропуск оценки роста в цикле 1: NULL, а не 0.

## Проверка

```bash
cd backend && .venv/Scripts/python -m pytest          # 86 тестов
cd frontend && npm test && npm run build              # node --test + tsc + сборка
```
