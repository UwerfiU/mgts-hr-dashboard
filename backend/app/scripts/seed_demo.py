"""Генерация синтетической демо-БД (WP6).

Запуск:  python -m app.scripts.seed_demo [--reset]

5 стажёров × 5 наставников (каждый наставник — за своего стажёра), циклы 1–6,
обе анкеты. Запись идёт через нормализацию WP2 (не в обход): идемпотентно по
source_key, повторный seed не создаёт дублей; --reset сначала очищает демо-данные
(включая неиспользуемых демо-участников).

Помимо источников `excel`/`form` синтетика помечается `source="demo"`: так её
можно безопасно удалить (`--reset`) и отличить от реальных данных.

«Сюжет» для демо:
  * «Демо Глеб» — стабильно слабые мотивация и удовлетворённость, низкая поддержка
    наставника; негативные комментарии в циклах 5–6 (вход для AI-анализа этапа 2);
  * «Демо Вера» — расхождение самооценки и оценки наставника по росту навыков
    (с цикла 3: стажёр 5, наставник 2) → блок comparison показывает устойчивый зазор;
  * «Демо Дарья» в цикле 1 пропустила оценку роста → NULL, а не 0.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Intern, Mentor, Submission
from ..normalization.core import normalize_and_store
from ..normalization.spec import SourceSpec
from ..sources.base import RawRecord

# Порядок важен: наставник i — за стажёра i (сюжет «слабый наставник» привязан к №5)
INTERN_ALIAS = ["Демо Анна", "Демо Борис", "Демо Вера", "Демо Дарья", "Демо Глеб"]
MENTOR_ALIAS = [f"Демо Наставник {i + 1}" for i in range(5)]
CYCLES = list(range(1, 7))

# Оценки стажёров по циклам 1–6 (None — пропуск → NULL)
INTERN_SCORES: dict[str, dict[str, list]] = {
    "Демо Анна":   {"skill_growth": [3, 4, 4, 5, 5, 5], "task_clarity": [3, 4, 4, 4, 5, 5],
                   "mentor_support": [4, 4, 5, 5, 5, 5], "motivation": [4, 4, 5, 5, 5, 5],
                   "satisfaction": [4, 4, 5, 5, 5, 5]},
    "Демо Борис":  {"skill_growth": [2, 3, 3, 4, 4, 5], "task_clarity": [3, 3, 4, 4, 4, 5],
                   "mentor_support": [4, 4, 4, 4, 5, 5], "motivation": [3, 3, 4, 4, 4, 4],
                   "satisfaction": [3, 4, 4, 4, 4, 5]},
    "Демо Вера":   {"skill_growth": [3, 4, 5, 5, 5, 5], "task_clarity": [4, 4, 4, 5, 5, 5],
                   "mentor_support": [4, 5, 5, 5, 5, 5], "motivation": [4, 4, 4, 5, 5, 5],
                   "satisfaction": [4, 5, 5, 5, 5, 5]},
    "Демо Глеб":   {"skill_growth": [2, 2, 3, 3, 3, 4], "task_clarity": [2, 2, 3, 3, 3, 3],
                   "mentor_support": [3, 3, 3, 2, 2, 2], "motivation": [2, 2, 2, 2, 2, 2],
                   "satisfaction": [3, 3, 2, 2, 2, 2]},
    "Демо Дарья":  {"skill_growth": [None, 3, 3, 4, 4, 4], "task_clarity": [3, 4, 4, 4, 5, 5],
                   "mentor_support": [4, 4, 4, 5, 5, 5], "motivation": [4, 4, 5, 5, 5, 5],
                   "satisfaction": [4, 4, 4, 5, 5, 5]},
}

INTERN_COMMENTS: dict[tuple[str, int], str] = {
    ("Демо Анна", 2): "Задачи интересные, наставник помогает.",
    ("Демо Глеб", 5): "Сложно понимать задачи, мало обратной связи.",
    ("Демо Глеб", 6): "Стало ещё сложнее: непонятно, что делать дальше и как оценивать свою работу.",
}

# Оценки наставников (наставник i — о стажёре i) по циклам 1–6
MENTOR_SCORES: dict[str, dict[str, list]] = {
    "Демо Наставник 1": {"performance": [3, 4, 4, 5, 5, 5], "proactivity": [3, 4, 4, 5, 5, 5],
                        "skill_growth_mentor": [3, 4, 4, 4, 5, 5], "communication": [4, 4, 5, 5, 5, 5],
                        "readiness": [2, 3, 3, 4, 4, 5]},
    "Демо Наставник 2": {"performance": [2, 3, 3, 4, 4, 4], "proactivity": [3, 3, 4, 4, 4, 5],
                        "skill_growth_mentor": [3, 3, 4, 4, 4, 5], "communication": [3, 4, 4, 4, 4, 5],
                        "readiness": [2, 2, 3, 3, 4, 4]},
    # Вера: самооценка роста 5 с цикла 3, наставник видит 2 → устойчивый зазор в comparison
    "Демо Наставник 3": {"performance": [3, 3, 3, 3, 3, 3], "proactivity": [3, 3, 4, 4, 4, 4],
                        "skill_growth_mentor": [3, 3, 2, 2, 2, 2], "communication": [4, 4, 4, 4, 5, 5],
                        "readiness": [3, 3, 3, 3, 4, 4]},
    "Демо Наставник 4": {"performance": [3, 3, 4, 4, 4, 5], "proactivity": [3, 4, 4, 4, 5, 5],
                        "skill_growth_mentor": [3, 3, 4, 4, 4, 4], "communication": [4, 4, 4, 5, 5, 5],
                        "readiness": [2, 3, 3, 4, 4, 5]},
    "Демо Наставник 5": {"performance": [2, 2, 2, 3, 3, 3], "proactivity": [2, 2, 2, 3, 3, 3],
                        "skill_growth_mentor": [2, 2, 2, 3, 3, 3], "communication": [2, 3, 3, 3, 3, 3],
                        "readiness": [1, 2, 2, 2, 3, 3]},
}

MENTOR_COMMENTS: dict[tuple[str, str, int], str] = {
    ("Демо Наставник 5", "Демо Глеб", 6): "Нужно больше поддержки: темп снизился, задачи усложняются.",
}

INTERN_SPEC = SourceSpec(
    source="demo", role="intern", questionnaire="intern_v1", cycle_field="month",
    field_map={f"q_{k}": k for k in INTERN_SCORES["Демо Анна"]} | {"comment_intern_text": "comment_intern"},
    about_intern_field="trainee_name",
)
MENTOR_SPEC = SourceSpec(
    source="demo", role="mentor", questionnaire="mentor_v1", cycle_field="month",
    field_map={f"q_{k}": k for k in MENTOR_SCORES["Демо Наставник 1"]} | {"comment_mentor_text": "comment_mentor"},
    about_intern_field="intern_name", author_mentor_field="mentor_name",
)


def build_records() -> tuple[list[RawRecord], list[RawRecord]]:
    """Определяемое построение всех демо-отправок (стажёрские и наставнические)."""
    intern_records: list[RawRecord] = []
    mentor_records: list[RawRecord] = []
    for i, alias in enumerate(INTERN_ALIAS):
        mentor = MENTOR_ALIAS[i]
        for c in CYCLES:
            payload: dict = {"month": c, "trainee_name": alias}
            for qk, series in INTERN_SCORES[alias].items():
                payload[f"q_{qk}"] = series[c - 1]
            if (alias, c) in INTERN_COMMENTS:
                payload["comment_intern_text"] = INTERN_COMMENTS[(alias, c)]
            intern_records.append(RawRecord("demo", f"demo:intern:{alias}:{c}", payload))

            mpayload: dict = {"month": c, "intern_name": alias, "mentor_name": mentor}
            for qk, series in MENTOR_SCORES[mentor].items():
                mpayload[f"q_{qk}"] = series[c - 1]
            if (mentor, alias, c) in MENTOR_COMMENTS:
                mpayload["comment_mentor_text"] = MENTOR_COMMENTS[(mentor, alias, c)]
            mentor_records.append(RawRecord("demo", f"demo:mentor:{mentor}:{alias}:{c}", mpayload))
    return intern_records, mentor_records


def _count(db: Session, role: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Submission).where(Submission.source == "demo", Submission.role == role)
    ) or 0


def _delete_unreferenced(db: Session, model, aliases: list[str], ref_column) -> None:
    """Удалить демо-участников с указанными псевдонимами, если на них больше нет ссылок."""
    for row in db.scalars(select(model).where(model.alias.in_(aliases))).all():
        used = db.scalar(
            select(func.count()).select_from(Submission).where(ref_column == row.id)
        )
        if not used:
            db.delete(row)


def run(db: Session, reset: bool = False) -> dict:
    """Сид демо-данных через нормализацию. Возвращает счётчики."""
    if reset:
        for s in db.scalars(select(Submission).where(Submission.source == "demo")):
            db.delete(s)  # ответы удаляются каскадом (cascade delete-orphan)
        db.flush()
        # Убираем и «фантомных» демо-людей, если на них не ссылаются другие данные:
        # иначе после смены псевдонимов в /meta остаются старые участники.
        _delete_unreferenced(db, Intern, INTERN_ALIAS, Submission.about_intern_id)
        _delete_unreferenced(db, Mentor, MENTOR_ALIAS, Submission.author_mentor_id)
        db.flush()

    intern_records, mentor_records = build_records()
    normalize_and_store(db, intern_records, INTERN_SPEC)
    normalize_and_store(db, mentor_records, MENTOR_SPEC)
    db.commit()
    return {"intern_submissions": _count(db, "intern"), "mentor_submissions": _count(db, "mentor")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Синтетическая демо-БД (5 стажёров × 5 наставников, циклы 1–6)")
    parser.add_argument("--reset", action="store_true", help="сначала очистить демо-данные")
    args = parser.parse_args(argv)

    from ..catalog.loader import load_catalog
    from ..db.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        load_catalog(db)
        stats = run(db, reset=args.reset)
        print(json.dumps({"ok": True, **stats}, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
