"""Динамика оценок по циклам (series) — WP5.

Точки упорядочены по циклам; пропущенный цикл — value: null (не 0);
n — число валидных наблюдений за цикл.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Metric
from .common import filtered_submissions, qids_for_role


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def points_for_questions(
    db: Session, role: str, question_keys: set[str],
    from_month: int, to_month: int,
    intern_id: int | None = None, mentor_id: int | None = None,
) -> list[dict]:
    qids = qids_for_role(db, role)
    points = []
    for m in range(from_month, to_month + 1):
        subs = filtered_submissions(db, qids, m, m, role, intern_id, mentor_id)
        scores = [
            a.score
            for s in subs
            for a in s.answers
            if a.question_key in question_keys and isinstance(a.score, (int, float))
        ]
        points.append({"month": m, "value": _mean(scores), "n": len(scores)})
    return points


def series(
    db: Session, metric: Metric, from_month: int, to_month: int,
    intern_id: int | None = None, mentor_id: int | None = None,
) -> list[dict]:
    """[{role, points:[{month, value|null, n}]}] для метрики."""
    return [{
        "role": metric.role,
        "points": points_for_questions(db, metric.role, set(metric.question_keys or []), from_month, to_month, intern_id, mentor_id),
    }]
