"""GET /api/v1/feedback — разрешённые к показу комментарии (контракт BACKEND.md).

Показ текстов управляется политикой (text_display_allowed): если запрещён —
403 + код TEXTS_NOT_ALLOWED (числовая аналитика при этом доступна).
Пустой срез — 200 + texts: [] (различается с запретом!).

В ответ намеренно НЕ попадают идентификаторы авторов: с 5 участниками
псевдоним + подробный текст раскрывают личность. AI-статус/сводки/сигналы
будут добавлены в WP9 тем же срезом.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ... import policy
from ...analytics.common import filtered_submissions, qids_for_role
from ...catalog.access import get_question
from ...config import settings
from ...db.database import get_db
from .codes import forbidden

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/feedback")
def feedback(
    db: Session = Depends(get_db),
    fromMonth: int = Query(1, ge=1, le=settings.program_months),
    toMonth: int = Query(settings.program_months, ge=1, le=settings.program_months),
    role: str | None = Query(default=None, pattern="^(intern|mentor)$"),
    categoryId: str | None = Query(default=None, description="ключ текстового вопроса из /api/v1/meta categories"),
    internId: str | None = Query(default=None),
):
    if not policy.texts_allowed():
        return forbidden("TEXTS_NOT_ALLOWED")

    intern_id = None
    if internId is not None:
        if not (policy.personal_slices_allowed() and policy.numeric_history_allowed()):
            return forbidden("PERSONAL_SLICE_NOT_ALLOWED")
        from ...db.models import Intern

        row = db.get(Intern, int(internId)) if str(internId).isdigit() else None
        if row is None:
            return {"texts": []}
        intern_id = row.id

    wanted = {r for r in ("intern", "mentor") if role is None or r == role}
    subs = []
    for r in wanted:
        rq = qids_for_role(db, r)
        if rq:
            subs.extend(filtered_submissions(db, rq, fromMonth, toMonth, r, intern_id=intern_id))

    texts = []
    for s in subs:
        for a in s.answers:
            if not a.text:
                continue
            question = get_question(db, a.question_key)
            if question is None or question.type != "text":
                continue
            if categoryId is not None and a.question_key != categoryId:
                continue
            texts.append({
                "month": s.cycle,
                "role": s.role,
                "questionKey": a.question_key,
                "text": a.text,
            })
    texts.sort(key=lambda t: (t["month"], t["role"]))
    return {"texts": texts}
