"""Доступ к каталогу для нормализации (WP2), аналитики (WP5) и API."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ComparisonPair, Metric, Question, Questionnaire


def get_question(db: Session, key: str) -> Question | None:
    return db.scalar(select(Question).where(Question.key == key))


def get_questions(db: Session, role: str | None = None, qid: str | None = None) -> list[Question]:
    q = select(Question)
    if qid is not None:
        q = q.where(Question.qid == qid)
    rows = list(db.scalars(q).all())
    if role is not None:
        allowed = {
            r.qid
            for r in db.scalars(select(Questionnaire).where(Questionnaire.role == role))
        }
        rows = [r for r in rows if r.qid in allowed]
    return sorted(rows, key=lambda r: (r.qid, r.key))


def get_scale(db: Session, key: str) -> tuple[int | None, int | None] | None:
    """Границы шкалы вопроса; None, если вопрос неизвестен каталогу."""
    q = get_question(db, key)
    if q is None:
        return None
    return q.scale_min, q.scale_max


def get_metric(db: Session, metric_id: str) -> Metric | None:
    return db.scalar(select(Metric).where(Metric.metric_id == metric_id))


def get_metrics(db: Session, role: str | None = None) -> list[Metric]:
    q = select(Metric)
    if role is not None:
        q = q.where(Metric.role == role)
    return list(db.scalars(q.order_by(Metric.metric_id)))


def metric_questions(db: Session, metric: Metric) -> list[Question]:
    out = []
    for key in metric.question_keys or []:
        q = get_question(db, key)
        if q is not None:
            out.append(q)
    return out


def get_comparison_pairs(db: Session) -> list[ComparisonPair]:
    return list(db.scalars(select(ComparisonPair).order_by(ComparisonPair.pair_id)))
