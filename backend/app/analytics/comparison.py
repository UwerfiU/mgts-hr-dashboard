"""Сравнение сопоставимых вопросов стажёр ↔ наставник (comparison) — WP5.

Считается ТОЛЬКО для явно настроенных пар (ComparisonPair из каталога):
средняя разность ВНУТРИ пар «стажёр × цикл» (не вычитание средних по всем ответам).
Если подтверждённых связей между людьми нет — парные расхождения недоступны.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ComparisonPair, Metric, Submission
from .common import filtered_submissions, qids_for_role


def find_pair_for_metric(db: Session, metric: Metric) -> ComparisonPair | None:
    keys = set(metric.question_keys or [])
    if not keys:
        return None
    if metric.role == "intern":
        return db.scalar(select(ComparisonPair).where(ComparisonPair.intern_question.in_(keys)))
    return db.scalar(select(ComparisonPair).where(ComparisonPair.mentor_question.in_(keys)))


def _score_by_intern(subs: list[Submission], question_key: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for s in subs:
        if s.about_intern_id is None:
            continue
        for a in s.answers:
            if a.question_key == question_key and isinstance(a.score, (int, float)):
                out[s.about_intern_id] = a.score
    return out


def comparison(
    db: Session, pair: ComparisonPair, from_month: int, to_month: int,
    intern_id: int | None = None, mentor_id: int | None = None,
) -> dict:
    """{status: available|unavailable, direction, points:[{month, value|null, nPairs}]}."""
    intern_qids = qids_for_role(db, "intern")
    mentor_qids = qids_for_role(db, "mentor")
    points = []
    total_pairs = 0
    for m in range(from_month, to_month + 1):
        i_subs = filtered_submissions(db, intern_qids, m, m, "intern", intern_id, mentor_id)
        m_subs = filtered_submissions(db, mentor_qids, m, m, "mentor", intern_id, mentor_id)
        i_scores = _score_by_intern(i_subs, pair.intern_question)
        m_scores = _score_by_intern(m_subs, pair.mentor_question)

        diffs: list[float] = []
        for iid, iv in i_scores.items():
            mv = m_scores.get(iid)
            if mv is None:
                continue
            diff = iv - mv if pair.direction == "intern_minus_mentor" else mv - iv
            diffs.append(diff)
        total_pairs += len(diffs)
        value = round(sum(diffs) / len(diffs), 2) if diffs else None
        points.append({"month": m, "value": value, "nPairs": len(diffs)})

    status = "available" if total_pairs > 0 else "unavailable"
    return {"status": status, "direction": pair.direction, "points": points}
