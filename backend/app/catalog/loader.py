"""Загрузка каталога анкет/вопросов/метрик из config/catalog.yaml (WP1).

БД — материализация конфига: при каждой загрузке — upsert по естественным ключам
и удаление устаревших записей (анкеты/вопросы/метрики/пары, которых нет в конфиге).
Ответы на удалённые вопросы сохраняются (данные с provenance), но становятся
невидимы для аналитики до повторного импорта.

Использование:
    from app.catalog.loader import load_catalog
    report = load_catalog(db)                  # путь по умолчанию из settings
    report = load_catalog(db, path="other.yaml")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import ComparisonPair, Metric, Question, Questionnaire

ROLES = ("intern", "mentor")
QUESTION_TYPES = ("score", "text")
DIRECTIONS = ("intern_minus_mentor", "mentor_minus_intern")
RULES = ("paired_mean",)


class CatalogConfigError(ValueError):
    """Некорректный конфиг каталога; все проблемы перечислены в сообщении."""


@dataclass
class LoadReport:
    questionnaires: int = 0
    questions: int = 0
    metrics: int = 0
    comparison_pairs: int = 0
    removed: list[str] = field(default_factory=list)  # "questionnaire:id", "question:key", ...


def _fail(problems: list[str]) -> None:
    raise CatalogConfigError("Ошибки каталога:\n" + "\n".join(f"  - {p}" for p in problems))


def validate(data: dict) -> None:
    """Полная структурная валидация конфига; собирает ВСЕ проблемы за один проход."""
    problems: list[str] = []

    questionnaires = data.get("questionnaires") or []
    if not questionnaires:
        problems.append("questionnaires: список пуст")
    qids: set[str] = set()
    for i, q in enumerate(questionnaires):
        path = f"questionnaires[{i}]"
        qid = q.get("id")
        role = q.get("role")
        version = q.get("version")
        if not isinstance(qid, str) or not qid:
            problems.append(f"{path}.id: не задан")
        elif qid in qids:
            problems.append(f"{path}.id: дубликат '{qid}'")
        else:
            qids.add(qid)
        if role not in ROLES:
            problems.append(f"{path}.role: '{role}' (допустимо: {', '.join(ROLES)})")
        if not isinstance(version, int):
            problems.append(f"{path}.version: ожидается целое число, получено: {version!r}")
        elif version < 1:
            problems.append(f"{path}.version: должно быть > 0, получено {version}")

    questions = data.get("questions") or []
    key_owner: dict[str, str] = {}
    for i, q in enumerate(questions):
        path = f"questions[{i}]"
        key = q.get("key")
        qid = q.get("questionnaire")
        if not isinstance(key, str) or not key:
            problems.append(f"{path}.key: не задан")
        elif key in key_owner:
            problems.append(
                f"{path}.key: '{key}' дублирует вопрос анкеты '{key_owner[key]}' (ключи глобально уникальны)"
            )
        else:
            key_owner[key] = qid
        if qid not in qids:
            problems.append(f"{path}.questionnaire: неизвестная анкета '{qid}'")
        qtype = q.get("type")
        if qtype not in QUESTION_TYPES:
            problems.append(f"{path}.type: '{qtype}' (допустимо: {', '.join(QUESTION_TYPES)})")
        elif qtype == "score":
            lo, hi = q.get("scale_min"), q.get("scale_max")
            if not isinstance(lo, int) or not isinstance(hi, int):
                problems.append(f"{path}: для type=score нужны целые scale_min/scale_max")
            elif lo > hi:
                problems.append(f"{path}: scale_min={lo} больше scale_max={hi}")

    intern_qids = {q["id"] for q in questionnaires if isinstance(q, dict) and q.get("role") == "intern"}
    mentor_qids = {q["id"] for q in questionnaires if isinstance(q, dict) and q.get("role") == "mentor"}
    key_qid: dict[str, str] = {}
    for q in questions:
        if isinstance(q, dict) and isinstance(q.get("key"), str):
            key_qid[q["key"]] = q.get("questionnaire")

    metrics = data.get("metrics") or []
    mid_seen: set[str] = set()
    for i, m in enumerate(metrics):
        path = f"metrics[{i}]"
        mid = m.get("id")
        if not isinstance(mid, str) or not mid:
            problems.append(f"{path}.id: не задан")
        elif mid in mid_seen:
            problems.append(f"{path}.id: дубликат '{mid}'")
        else:
            mid_seen.add(mid)
        if m.get("role") not in ROLES:
            problems.append(f"{path}.role: '{m.get('role')}' (допустимо: {', '.join(ROLES)})")
        metric_role = m.get("role")
        role_qids = intern_qids if metric_role == "intern" else mentor_qids
        for k in m.get("question_keys") or []:
            if k not in key_owner:
                problems.append(f"{path}.question_keys: неизвестный вопрос '{k}'")
            elif key_qid.get(k) not in role_qids:
                problems.append(
                    f"{path}.question_keys: вопрос '{k}' принадлежит анкете "
                    f"'{key_qid.get(k)}', а метрика объявлена для роли '{metric_role}'"
                )

    pairs = data.get("comparison_pairs") or []
    pid_seen: set[str] = set()
    for i, p in enumerate(pairs):
        path = f"comparison_pairs[{i}]"
        pid = p.get("id")
        if not isinstance(pid, str) or not pid:
            problems.append(f"{path}.id: не задан")
        elif pid in pid_seen:
            problems.append(f"{path}.id: дубликат '{pid}'")
        else:
            pid_seen.add(pid)
        ik, mk = p.get("intern_question"), p.get("mentor_question")
        if key_qid.get(ik) not in intern_qids:
            problems.append(f"{path}.intern_question: '{ik}' не является вопросом анкеты стажёра")
        if key_qid.get(mk) not in mentor_qids:
            problems.append(f"{path}.mentor_question: '{mk}' не является вопросом анкеты наставника")
        if p.get("direction", "intern_minus_mentor") not in DIRECTIONS:
            problems.append(
                f"{path}.direction: '{p.get('direction')}' (допустимо: {', '.join(DIRECTIONS)})"
            )
        if p.get("rule", "paired_mean") not in RULES:
            problems.append(f"{path}.rule: '{p.get('rule')}' (допустимо: {', '.join(RULES)})")

    if problems:
        _fail(problems)


def _upsert(db: Session, model, natural: dict[str, object], values: dict) -> None:
    conds = [getattr(model, k) == v for k, v in natural.items()]
    obj = db.scalar(select(model).where(*conds))
    if obj is None:
        db.add(model(**natural, **values))
    else:
        for k, v in values.items():
            setattr(obj, k, v)


def _drop_stale(db: Session, model, natural_key: str, config_ids: set[str], kind: str, report: LoadReport) -> None:
    for row in db.scalars(select(model)).all():
        current = getattr(row, natural_key)
        if current not in config_ids:
            db.delete(row)
            report.removed.append(f"{kind}:{current}")


def load_catalog(db: Session, path: str | Path | None = None) -> LoadReport:
    """Загрузить каталог из YAML в БД (идемпотентно). Бросает CatalogConfigError при невалидном конфиге."""
    p = Path(path) if path else Path(settings.catalog_path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    validate(data)
    report = LoadReport()

    # Порядок: сначала upsert всех родителей (анкет), затем детей (вопросов),
    # удаление устаревшего — наоборот, сначала дети (у вопросов есть FK на анкеты).
    qids = {q["id"] for q in data.get("questionnaires") or []}
    for q in data.get("questionnaires") or []:
        _upsert(db, Questionnaire, {"qid": q["id"]}, {"role": q["role"], "version": q["version"]})

    keys = {q["key"] for q in data.get("questions") or []}
    for q in data.get("questions") or []:
        values: dict = {"label": q.get("label", ""), "type": q["type"]}
        if q["type"] == "score":
            values.update(scale_min=q["scale_min"], scale_max=q["scale_max"])
        else:
            values.update(scale_min=None, scale_max=None)
        _upsert(db, Question, {"qid": q["questionnaire"], "key": q["key"]}, values)
    _drop_stale(db, Question, "key", keys, "question", report)
    # Орфаны: вопрос с ключом из конфига, но под старой id анкеты (переименование анкеты)
    for row in db.scalars(select(Question).where(Question.qid.not_in(qids))).all():
        db.delete(row)
        report.removed.append(f"question:{row.key}")
    _drop_stale(db, Questionnaire, "qid", qids, "questionnaire", report)

    mids = {m["id"] for m in data.get("metrics") or []}
    for m in data.get("metrics") or []:
        _upsert(
            db, Metric, {"metric_id": m["id"]},
            {"role": m["role"], "question_keys": list(m.get("question_keys") or [])},
        )
    _drop_stale(db, Metric, "metric_id", mids, "metric", report)

    pids = {p_["id"] for p_ in data.get("comparison_pairs") or []}
    for p_ in data.get("comparison_pairs") or []:
        _upsert(
            db, ComparisonPair, {"pair_id": p_["id"]},
            {
                "intern_question": p_["intern_question"],
                "mentor_question": p_["mentor_question"],
                "direction": p_.get("direction", "intern_minus_mentor"),
                "rule": p_.get("rule", "paired_mean"),
            },
        )
    _drop_stale(db, ComparisonPair, "pair_id", pids, "comparison_pair", report)

    db.commit()
    report.questionnaires = len(qids)
    report.questions = len(keys)
    report.metrics = len(mids)
    report.comparison_pairs = len(pids)
    return report
