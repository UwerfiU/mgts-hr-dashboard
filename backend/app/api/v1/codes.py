"""Коды недоступности и служебные ответы (контракт BACKEND.md).

Важно для фронта: «пустой срез» (200 + пустые данные) и «запрещённая
детализация» (403 + code) — РАЗНЫЕ состояния.
"""
from fastapi.responses import JSONResponse

CODE_PERSONAL_SLICE_NOT_ALLOWED = "PERSONAL_SLICE_NOT_ALLOWED"
CODE_TEXTS_NOT_ALLOWED = "TEXTS_NOT_ALLOWED"
CODE_METRIC_NOT_FOUND = "METRIC_NOT_FOUND"
CODE_BAD_MONTH_RANGE = "BAD_MONTH_RANGE"

MESSAGES = {
    CODE_PERSONAL_SLICE_NOT_ALLOWED: (
        "Персональные срезы недоступны: связь «ответ → человек» не подтверждена "
        "или показ истории запрещён политикой."
    ),
    CODE_TEXTS_NOT_ALLOWED: (
        "Показ текстовых комментариев запрещён политикой; числовая аналитика доступна."
    ),
    CODE_METRIC_NOT_FOUND: "Метрика не найдена в каталоге.",
    CODE_BAD_MONTH_RANGE: "Некорректный диапазон циклов.",
}


def forbidden(code: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"code": code, "message": MESSAGES.get(code, code)})


def not_found(code: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"code": code, "message": MESSAGES.get(code, code)})


def bad_request(code: str) -> JSONResponse:
    return JSONResponse(status_code=422, content={"code": code, "message": MESSAGES.get(code, code)})
