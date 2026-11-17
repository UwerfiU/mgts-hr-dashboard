"""GET /api/v1/metrics — охват, динамика, распределение, сравнение (контракт BACKEND.md)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ... import policy
from ...analytics import comparison as comparison_mod
from ...analytics import coverage as coverage_mod
from ...analytics import distribution as distribution_mod
from ...analytics import series as series_mod
from ...catalog import access
from ...config import settings
from ...db.database import get_db
from ...db.models import Intern, Mentor
from .codes import CODE_BAD_MONTH_RANGE, CODE_METRIC_NOT_FOUND, bad_request, forbidden, not_found

router = APIRouter(prefix="/api/v1", tags=["v1"])


def _resolve_person(db: Session, kind: str, opaque_id: str) -> int | None:
    model = Intern if kind == "intern" else Mentor
    row = db.get(model, int(opaque_id)) if str(opaque_id).isdigit() else None
    return row.id if row else None


@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
    metricId: str = Query(..., description="metricId из /api/v1/meta"),
    fromMonth: int = Query(1, ge=1, le=settings.program_months),
    toMonth: int = Query(settings.program_months, ge=1, le=settings.program_months),
    internId: str | None = Query(default=None, description="непрозрачный код стажёра"),
    mentorId: str | None = Query(default=None, description="непрозрачный код наставника"),
):
    if fromMonth > toMonth:
        return bad_request(CODE_BAD_MONTH_RANGE)

    metric = access.get_metric(db, metricId)
    if metric is None:
        return not_found(CODE_METRIC_NOT_FOUND)

    # Персональные срезы — только при подтверждённой связи и разрешении политикой
    intern_id = mentor_id = None
    if internId or mentorId:
        if not (policy.personal_slices_allowed() and policy.numeric_history_allowed()):
            return forbidden("PERSONAL_SLICE_NOT_ALLOWED")
        if internId:
            intern_id = _resolve_person(db, "intern", internId)
            if intern_id is None:
                return not_found(CODE_METRIC_NOT_FOUND)
        else:
            mentor_id = _resolve_person(db, "mentor", mentorId)
            if mentor_id is None:
                return not_found(CODE_METRIC_NOT_FOUND)

    result: dict = {
        "dataMode": settings.data_mode,
        "metricId": metric.metric_id,
        "coverage": coverage_mod.coverage(db, fromMonth, toMonth, intern_id, mentor_id),
        "series": series_mod.series(db, metric, fromMonth, toMonth, intern_id, mentor_id),
        "distribution": distribution_mod.distribution(db, metric, fromMonth, toMonth, intern_id, mentor_id),
    }

    # Сравнение — только для явно настроенных пар; плюс линия роли-партнёра в series
    pair = comparison_mod.find_pair_for_metric(db, metric)
    if pair is not None:
        result["comparison"] = comparison_mod.comparison(db, pair, fromMonth, toMonth, intern_id, mentor_id)
        counterpart_role = "mentor" if metric.role == "intern" else "intern"
        counterpart_key = pair.mentor_question if metric.role == "intern" else pair.intern_question
        result["series"].append({
            "role": counterpart_role,
            "points": series_mod.points_for_questions(
                db, counterpart_role, {counterpart_key}, fromMonth, toMonth, intern_id, mentor_id
            ),
        })
    else:
        result["comparison"] = {"status": "not_configured", "direction": None, "points": []}

    return result
