"""Охват ответов по ролям (coverage) — WP5."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import policy
from ..db.models import Submission
from .common import filtered_submissions, qids_for_role


def coverage(
    db: Session, from_month: int, to_month: int,
    intern_id: int | None = None, mentor_id: int | None = None,
) -> dict[str, dict]:
    """{role: {submitted, expected}}.

    expected — план ответов на срез (план на цикл × число циклов);
    null, если план неизвестен; для персональных срезов план не моделируется → null.
    """
    plan = policy.expected_per_cycle()
    n_months = to_month - from_month + 1
    out: dict[str, dict] = {}
    for role in ("intern", "mentor"):
        subs = filtered_submissions(
            db, qids_for_role(db, role), from_month, to_month, role, intern_id, mentor_id
        )
        expected: int | None = None
        if plan is not None and intern_id is None and mentor_id is None:
            per = plan.get(role)
            if per is not None:
                expected = per * n_months
        out[role] = {"submitted": len(subs), "expected": expected}
    return out
