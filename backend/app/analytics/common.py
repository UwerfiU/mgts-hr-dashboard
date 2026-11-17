"""Общие помощники срезов данных для аналитики (WP5)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Questionnaire, Submission


def qids_for_role(db: Session, role: str) -> set[str]:
    return {qn.qid for qn in db.scalars(select(Questionnaire).where(Questionnaire.role == role))}


def linked_intern_ids(db: Session, mentor_id: int) -> set[int]:
    """Стажёры, «о которых» отвечал данный наставник (подтверждённая связь)."""
    rows = db.scalars(
        select(Submission.about_intern_id).where(
            Submission.author_mentor_id == mentor_id,
            Submission.about_intern_id.is_not(None),
        )
    )
    return {r for r in rows if r is not None}


def filtered_submissions(
    db: Session,
    qids: set[str],
    from_month: int,
    to_month: int,
    role: str,
    intern_id: int | None = None,
    mentor_id: int | None = None,
) -> list[Submission]:
    """Отправки по анкетам роли, срезу циклов и персональному фильтру.

    * intern_id — только ответы «о» этом стажёре (обе роли);
    * mentor_id — связанные пары «стажёр × цикл»: для role=mentor — только ответы
      этого наставника с подтверждённой связью; для role=intern — ответы о его стажёрах.
    """
    if not qids:
        return []
    q = select(Submission).where(
        Submission.questionnaire.in_(qids),
        Submission.cycle >= from_month,
        Submission.cycle <= to_month,
    )
    if intern_id is not None:
        q = q.where(Submission.about_intern_id == intern_id)
    elif mentor_id is not None:
        linked = linked_intern_ids(db, mentor_id)
        if not linked:
            return []
        if role == "mentor":
            q = q.where(
                Submission.author_mentor_id == mentor_id,
                Submission.about_intern_id.in_(linked),
            )
        else:
            q = q.where(Submission.about_intern_id.in_(linked))
    return list(db.scalars(q.order_by(Submission.cycle)))
