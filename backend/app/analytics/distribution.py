"""Распределение оценок выбранного показателя (distribution) — WP5."""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from ..db.models import Metric
from .common import filtered_submissions, qids_for_role


def distribution(
    db: Session, metric: Metric, from_month: int, to_month: int,
    intern_id: int | None = None, mentor_id: int | None = None,
) -> list[dict]:
    """[{role, buckets:[{score, count}]}] — по целым значениям (округление)."""
    subs = filtered_submissions(
        db, qids_for_role(db, metric.role), from_month, to_month, metric.role, intern_id, mentor_id
    )
    keys = set(metric.question_keys or [])
    counts: Counter[int] = Counter()
    for s in subs:
        for a in s.answers:
            if a.question_key in keys and isinstance(a.score, (int, float)):
                counts[int(round(a.score))] += 1
    return [{
        "role": metric.role,
        "buckets": [{"score": score, "count": count} for score, count in sorted(counts.items())],
    }]
