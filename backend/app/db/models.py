# TODO(WP1): заменить на нормализованную модель по PLAN.md §3
# (Questionnaire/Question/Metric/ComparisonPair/Intern/Mentor/Submission/Answer/SyncState).
# Текущие модели — временный вариант из начального скелета.
"""ORM-модели данных."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Trainee(Base):
    """Стажёр программы."""

    __tablename__ = "trainees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    responses: Mapped[list["Response"]] = relationship(back_populates="trainee")
    signals: Mapped[list["Signal"]] = relationship(back_populates="trainee")


class Mentor(Base):
    """Наставник."""

    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Pair(Base):
    """Связка «стажёр ↔ наставник» (в программе 5 и 5, т.е. 1:1)."""

    __tablename__ = "pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id"), unique=True, index=True)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("mentors.id"), unique=True, index=True)

    trainee: Mapped["Trainee"] = relationship()
    mentor: Mapped["Mentor"] = relationship()


class Response(Base):
    """Ответ на ежемесячный опрос (форма стажёра или формы наставника).

    Уникальность: один ответ на (тип респондента, стажёр, месяц) — повторная
    отправка той же пары обновляет запись (идемпотентность вебхука).
    """

    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("respondent_type", "trainee_id", "month", name="uq_response"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    respondent_type: Mapped[str] = mapped_column(String(16), index=True)  # trainee | mentor
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id"), index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)  # месяц программы, 1..6

    ratings: Mapped[dict] = mapped_column(JSON, default=dict)  # {question_key: число}
    comment: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict | None] = mapped_column(JSON)  # исходный payload формы как есть
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    trainee: Mapped["Trainee"] = relationship(back_populates="responses")


class CommentInsight(Base):
    """Результат AI-анализа текстового комментария."""

    __tablename__ = "comment_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("responses.id"), unique=True, index=True)
    sentiment_score: Mapped[float] = mapped_column(default=0.0)  # -1..1
    sentiment_label: Mapped[str] = mapped_column(String(16), default="neutral")  # positive|neutral|negative
    risk_level: Mapped[str] = mapped_column(String(16), default="low")  # low|medium|high
    issues: Mapped[list] = mapped_column(JSON, default=list)  # ["проблема 1", ...]
    summary: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(16), default="none")  # llm|lexicon|none


class Signal(Base):
    """Сигнал о потенциальной проблеме по стажёру за месяц (с причиной)."""

    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("trainee_id", "month", "type", name="uq_signal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id"), index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32))  # low_rating|rating_drop|divergence|downward_trend|negative_comment
    severity: Mapped[str] = mapped_column(String(16))  # low|medium|high
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)  # человекочитаемая причина
    source: Mapped[str] = mapped_column(String(16), default="rule")  # rule|ai
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    trainee: Mapped["Trainee"] = relationship(back_populates="signals")
