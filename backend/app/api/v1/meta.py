"""GET /api/v1/meta — справочники, режим данных, права, статус синхронизации."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import policy
from ...db.models import Intern, Mentor
from ...catalog import access
from ...config import settings
from ...db.database import get_db
from ...sources.forms_poller.sync_state import get_sync_states

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    personal_ok = policy.personal_slices_allowed()

    metrics_out = []
    for m in access.get_metrics(db):
        questions = access.metric_questions(db, m)
        scales = [(q.scale_min, q.scale_max) for q in questions if q.type == "score"]
        scale = None
        if scales:
            lo = min(s[0] for s in scales if s[0] is not None) if any(s[0] is not None for s in scales) else None
            hi = max(s[1] for s in scales if s[1] is not None) if any(s[1] is not None for s in scales) else None
            scale = {"min": lo, "max": hi}
        metrics_out.append({
            "metricId": m.metric_id,
            "role": m.role,
            "label": questions[0].label if questions else m.metric_id,
            "scale": scale,
            "questions": [{"key": q.key, "label": q.label} for q in questions],
        })

    categories = []
    for role in ("intern", "mentor"):
        for q in access.get_questions(db, role=role):
            if q.type == "text":
                categories.append({"id": q.key, "label": q.label, "role": role})

    aliases = {
        "allowed": personal_ok,
        # псевдонимы отдаём только при разрешённых персональных срезах
        "interns": sorted({i.alias for i in db.scalars(select(Intern))}) if personal_ok else [],
        "mentors": sorted({m.alias for m in db.scalars(select(Mentor))}) if personal_ok else [],
    }

    return {
        "dataMode": settings.data_mode,
        "cycles": list(range(1, settings.program_months + 1)),
        "metrics": metrics_out,
        "aliases": aliases,
        "categories": categories,
        "detailPermissions": {
            "personalSlicesAllowed": personal_ok,
            "numericHistoryAllowed": policy.numeric_history_allowed(),
            "textsAllowed": policy.texts_allowed(),
        },
        "aiAvailable": bool(settings.llm_api_key),  # WP9: расширить статусами анализа
        "sync": [
            {
                "connector": s.connector,
                "lastSuccessAt": s.last_success_at.isoformat() if s.last_success_at else None,
                "lastError": s.last_error,
            }
            for s in get_sync_states(db)
        ],
    }
