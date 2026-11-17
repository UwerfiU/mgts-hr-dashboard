"""Нормализованная ORM-модель данных (PLAN.md §3, задание WP1).

Сущности:
  * каталог: Questionnaire → Question; Metric; ComparisonPair —
    материализация config/catalog.yaml (синхронизирует app.catalog.loader);
  * участники: Intern / Mentor (непрозрачные стабильные коды + псевдонимы);
  * данные: Submission (отправка с provenance) → Answer (ответ на вопрос);
  * инфраструктура: SyncState (статус коннекторов).

Принципы:
  * уникальность отправки — по (source, source_key): основа идемпотентности;
  * связь «о ком» (about_intern_id) опциональна: отправка без связи хранится
    и учитывается в агрегатах, но не попадает в персональные срезы;
  * пропуск оценки — Answer.score = NULL (никогда не 0).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Каталог (материализация config/catalog.yaml) ---------------------------


class Questionnaire(Base):
    """Анкета: роль + версия. qid — ключ из конфига (напр. "intern_v1")."""

    __tablename__ = "questionnaires"

    id: Mapped[int] = mapped_column(primary_key=True)
    qid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # intern | mentor
    version: Mapped[int] = mapped_column(Integer, default=1)

    questions: Mapped[list["Question"]] = relationship(back_populates="questionnaire")


class Question(Base):
    """Вопрос анкеты. Ключ глобально уникален (упрощает ссылки метрик и ответов)."""

    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("qid", "key", name="uq_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    qid: Mapped[str] = mapped_column(String(64), ForeignKey("questionnaires.qid"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(16))  # score | text
    scale_min: Mapped[int | None] = mapped_column(Integer)
    scale_max: Mapped[int | None] = mapped_column(Integer)

    questionnaire: Mapped["Questionnaire"] = relationship(back_populates="questions")


class Metric(Base):
    """Показатель для /api/v1/metrics: metricId → вопросы."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # intern | mentor
    question_keys: Mapped[list] = mapped_column(JSON, default=list)


class ComparisonPair(Base):
    """Явно настроенная пара сопоставимых вопросов для блока comparison."""

    __tablename__ = "comparison_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pair_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    intern_question: Mapped[str] = mapped_column(String(64))
    mentor_question: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(32), default="intern_minus_mentor")
    rule: Mapped[str] = mapped_column(String(32), default="paired_mean")


# --- Участники ----------------------------------------------------------------


class Intern(Base):
    """Стажёр. opaque_id — стабильный непрозрачный код, alias — псевдоним для дашборда."""

    __tablename__ = "interns"

    id: Mapped[int] = mapped_column(primary_key=True)
    opaque_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    alias: Mapped[str] = mapped_column(String(200))


class Mentor(Base):
    """Наставник."""

    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(primary_key=True)
    opaque_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    alias: Mapped[str] = mapped_column(String(200))


# --- Данные --------------------------------------------------------------------


class Submission(Base):
    """Отправка (ответ на анкету) с provenance.

    source_key — ключ записи в источнике: для форм formId+responseId,
    для Excel — по правилу из конфига (file_row_hash / stable_id).
    Уникальность (source, source_key) = идемпотентность импорта/синхронизации.
    """

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("source", "source_key", name="uq_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # excel | form
    source_key: Mapped[str] = mapped_column(String(200), index=True)
    questionnaire: Mapped[str] = mapped_column(String(64), index=True)  # qid анкеты
    cycle: Mapped[int] = mapped_column(Integer, index=True)  # цикл программы, 1–6
    role: Mapped[str] = mapped_column(String(16), index=True)  # intern | mentor
    about_intern_id: Mapped[int | None] = mapped_column(
        ForeignKey("interns.id"), nullable=True, index=True
    )
    author_mentor_id: Mapped[int | None] = mapped_column(
        ForeignKey("mentors.id"), nullable=True, index=True
    )  # кто отвечал (для role=mentor); нужен для фильтра «по наставнику»
    file_batch_id: Mapped[str | None] = mapped_column(String(64))  # для Excel-партий (замена партии)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    answers: Mapped[list["Answer"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class Answer(Base):
    """Ответ на конкретный вопрос внутри отправки."""

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_key", name="uq_answer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    question_key: Mapped[str] = mapped_column(String(64))
    score: Mapped[float | None] = mapped_column(Float)  # NULL = пропуск (не 0!)
    text: Mapped[str | None] = mapped_column(Text)

    submission: Mapped["Submission"] = relationship(back_populates="answers")


class SyncState(Base):
    """Статус коннектора синхронизации (для /api/v1/meta и диагностики)."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
