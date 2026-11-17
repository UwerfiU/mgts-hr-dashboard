"""Общая нормализация: RawRecord + SourceSpec → каноническая запись → БД (WP2).

Принципы (BACKEND.md, B2):
  * два разных входных формата дают одинаковый тип записи;
  * отклонённые строки видны в отчёте с причиной;
  * пропуск оценки не превращается в ноль (Answer.score = NULL);
  * provenance: источник, ключ в источнике, batch.

Точка входа для коннекторов (WP3/WP4): `normalize_and_store(db, records, spec)`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..catalog import access
from ..config import settings
from ..db.models import Answer, Intern, Mentor, Questionnaire, Submission
from ..sources.base import RawRecord
from .report import NormalizationReport
from .spec import SourceSpec


@dataclass
class AnswerValue:
    score: float | None = None
    text: str | None = None


@dataclass
class NormalizedRecord:
    """Каноническая запись — единый тип после нормализации любого источника."""

    source: str
    source_key: str
    role: str
    questionnaire: str
    cycle: int
    about_intern: str | None  # псевдоним; в Intern разрешается при сохранении
    author_mentor: str | None = None  # псевдоним автора (для role=mentor)
    answers: dict[str, AnswerValue] = field(default_factory=dict)
    submitted_at: datetime | None = None
    file_batch_id: str | None = None


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_cycle_int(value: Any) -> int | None:
    """Цикл из источника: 3, '3', 3.0 → 3; 'x', 3.5, пусто → None."""
    if _empty(value):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    i = int(f)
    return i if i == f else None


def normalize_record(
    db: Session, raw: RawRecord, spec: SourceSpec
) -> tuple[NormalizedRecord | None, list[str]]:
    """Сырая запись → каноническая. Возвращает (record, причины); причины не пусты — запись отклонена."""
    payload = raw.payload or {}

    qn = db.scalar(select(Questionnaire).where(Questionnaire.qid == spec.questionnaire))
    if qn is None:
        return None, [f"анкета '{spec.questionnaire}' не найдена в каталоге"]

    cycle = _to_cycle_int(payload.get(spec.cycle_field))
    if cycle is None or not 1 <= cycle <= settings.program_months:
        return None, [
            f"цикл: значение {payload.get(spec.cycle_field)!r} "
            f"(поле '{spec.cycle_field}') не число от 1 до {settings.program_months}"
        ]

    reasons: list[str] = []
    answers: dict[str, AnswerValue] = {}
    for raw_field, qkey in spec.field_map.items():
        question = access.get_question(db, qkey)
        if question is None:
            reasons.append(f"вопрос '{qkey}' (поле '{raw_field}') не найден в каталоге")
            continue
        value = payload.get(raw_field)
        if _empty(value):
            if question.type == "score":
                answers[qkey] = AnswerValue(score=None)  # пропуск → NULL, никогда не 0
            continue
        if question.type == "score":
            try:
                score = float(value)
            except (TypeError, ValueError):
                reasons.append(f"оценка по вопросу '{qkey}' не число: {value!r}")
                continue
            lo, hi = question.scale_min, question.scale_max
            if (lo is not None and score < lo) or (hi is not None and score > hi):
                reasons.append(f"оценка {score:g} по вопросу '{qkey}' вне шкалы {lo:g}–{hi:g}")
                continue
            answers[qkey] = AnswerValue(score=score)
        else:  # text
            answers[qkey] = AnswerValue(text=str(value).strip())

    if reasons:
        return None, reasons

    about: str | None = None
    if spec.about_intern_field:
        v = payload.get(spec.about_intern_field)
        if not _empty(v):
            about = str(v).strip()

    author_mentor: str | None = None
    if spec.role == "mentor" and spec.author_mentor_field:
        v = payload.get(spec.author_mentor_field)
        if not _empty(v):
            author_mentor = str(v).strip()

    submitted_at = raw.submitted_at
    if submitted_at is None and spec.submitted_at_field:
        v = payload.get(spec.submitted_at_field)
        if not _empty(v):
            try:
                submitted_at = datetime.fromisoformat(str(v).strip())
            except ValueError:
                pass  # нераспознанная дата — не критично, оставляем None

    return (
        NormalizedRecord(
            source=raw.source,
            source_key=raw.source_key,
            role=spec.role,
            questionnaire=spec.questionnaire,
            cycle=cycle,
            about_intern=about,
            author_mentor=author_mentor,
            answers=answers,
            submitted_at=submitted_at,
            file_batch_id=raw.file_batch_id,
        ),
        [],
    )


def resolve_intern(db: Session, alias: str) -> Intern:
    """Псевдоним → Intern; при отсутствии создаёт со стабильным непрозрачным id."""
    intern = db.scalar(select(Intern).where(Intern.alias == alias))
    if intern is None:
        opaque = "AUTO-" + hashlib.sha1(alias.encode("utf-8")).hexdigest()[:8]
        intern = Intern(opaque_id=opaque, alias=alias)
        db.add(intern)
        db.flush()
    return intern


def resolve_mentor(db: Session, alias: str) -> Mentor:
    """Псевдоним → Mentor; при отсутствии создаёт со стабильным непрозрачным id."""
    mentor = db.scalar(select(Mentor).where(Mentor.alias == alias))
    if mentor is None:
        opaque = "AUTO-" + hashlib.sha1(alias.encode("utf-8")).hexdigest()[:8]
        mentor = Mentor(opaque_id=opaque, alias=alias)
        db.add(mentor)
        db.flush()
    return mentor


def store_record(db: Session, rec: NormalizedRecord) -> bool:
    """Upsert отправки по (source, source_key). True — создана новая."""
    sub = db.scalar(
        select(Submission).where(
            Submission.source == rec.source,
            Submission.source_key == rec.source_key,
        )
    )
    created = sub is None
    if created:
        sub = Submission(source=rec.source, source_key=rec.source_key)
        db.add(sub)

    sub.questionnaire = rec.questionnaire
    sub.cycle = rec.cycle
    sub.role = rec.role
    sub.file_batch_id = rec.file_batch_id
    sub.submitted_at = rec.submitted_at
    sub.about_intern_id = resolve_intern(db, rec.about_intern).id if rec.about_intern else None
    sub.author_mentor_id = (
        resolve_mentor(db, rec.author_mentor).id if rec.role == "mentor" and rec.author_mentor else None
    )
    db.flush()

    # Ответы на вопросы: полная замена (повторное чтение обновляет значения, не дублирует).
    # Bulk-DELETE: ORM-коллекция sub.answers может быть stale (expire_on_commit=False),
    # поэтому опираемся на БД, а не на состояние в памяти.
    db.execute(delete(Answer).where(Answer.submission_id == sub.id))
    for qkey, val in rec.answers.items():
        db.add(Answer(submission_id=sub.id, question_key=qkey, score=val.score, text=val.text))
    return created


def normalize_batch(
    db: Session, records: list[RawRecord], spec: SourceSpec
) -> tuple[list[NormalizedRecord], NormalizationReport]:
    """Нормализация пакета БЕЗ сохранения (dry-run и основа normalize_and_store).

    Возвращает (принятые канонические записи, отчёт о пропущенных/ошибках).
    """
    report = NormalizationReport()
    ok_records: list[NormalizedRecord] = []
    for raw in records:
        try:
            rec, reasons = normalize_record(db, raw, spec)
        except Exception as e:  # noqa: BLE001 — защита от непредвиденного в одной строке
            db.rollback()
            report.error(raw.source_key, f"непредвиденная ошибка: {e}")
            continue
        if rec is None:
            for reason in reasons:
                report.skip(raw.source_key, reason)
            continue
        ok_records.append(rec)
    return ok_records, report


def normalize_and_store(
    db: Session, records: list[RawRecord], spec: SourceSpec
) -> NormalizationReport:
    """Пакетный путь для коннекторов: нормализация + сохранение.

    Коммит — на каждую принятую запись: одна битая строка не роняет партию.
    """
    ok_records, report = normalize_batch(db, records, spec)
    for rec in ok_records:
        try:
            created = store_record(db, rec)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            report.error(rec.source_key, f"не удалось сохранить: {e}")
            continue
        report.accepted += 1
        if created:
            report.created += 1
        else:
            report.updated += 1
    return report
