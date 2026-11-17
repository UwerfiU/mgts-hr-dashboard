"""Сигналы о проблемах (этап 2 / WP8): детерминированные правила по `Submission/Answer`.

Модуль намеренно не хранит сигналы в БД и не подключён к API: это чистые
аналитические функции, которые можно вызывать из `/feedback` (или отдельного
маршрута) после согласования с фронтендом.

Правила (source="rule"):
  * low_rating      — оценка ≤ порога (в анкете стажёра или наставника);
  * rating_drop     — падение оценки к прошлому циклу на ≥ порога;
  * divergence      — расхождение оценок стажёра и наставника по паре из каталога;
  * downward_trend  — средняя самооценка снижается N циклов подряд.

AI (source="ai") — только если снаружи передан готовый результат анализа
комментариев (`insights`), чтобы модуль не зависел от хранилища AI-результатов:
  * negative_comment — негативный sentiment / высокий риск.

Возвращаемые сигналы — словари:
    {type, severity, month, title, reason, source, role?, questionKey?, internId?}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ComparisonPair, Intern, Question, Submission

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
WHO = {"intern": "Стажёр", "mentor": "Наставник"}


@dataclass(frozen=True)
class Thresholds:
    low_rating_max: float = 2.0
    low_rating_high: float = 1.0
    drop_min: float = 2.0
    drop_high: float = 3.0
    divergence_min: float = 2.0
    divergence_high: float = 3.0
    trend_months: int = 3


def _labels(db: Session) -> dict[str, str]:
    return {q.key: q.label for q in db.scalars(select(Question))}


def _signal(
    type_: str,
    severity: str,
    month: int,
    title: str,
    reason: str,
    *,
    source: str = "rule",
    role: str | None = None,
    question_key: str | None = None,
    intern_id: int | None = None,
) -> dict:
    out = {
        "type": type_,
        "severity": severity,
        "month": month,
        "title": title,
        "reason": reason,
        "source": source,
    }
    if role is not None:
        out["role"] = role
    if question_key is not None:
        out["questionKey"] = question_key
    if intern_id is not None:
        out["internId"] = intern_id
    return out


def _mean_by_month(subs: Iterable[Submission]) -> dict[int, dict[str, float]]:
    """{month: {question_key: среднее}} — по всем отправкам роли (несколько ответов усредняются)."""
    acc: dict[int, dict[str, list[float]]] = {}
    for s in subs:
        for a in s.answers:
            if isinstance(a.score, (int, float)):
                acc.setdefault(s.cycle, {}).setdefault(a.question_key, []).append(float(a.score))
    return {
        month: {key: sum(vals) / len(vals) for key, vals in keys.items()}
        for month, keys in acc.items()
    }


def _signals_for_intern(
    db: Session,
    subs: list[Submission],
    labels: dict[str, str],
    pairs: list[ComparisonPair],
    th: Thresholds,
) -> list[dict]:
    intern_ids = {s.about_intern_id for s in subs if s.about_intern_id is not None}
    intern_id = next(iter(intern_ids)) if len(intern_ids) == 1 else None

    by_role: dict[str, list[Submission]] = {"intern": [], "mentor": []}
    for s in subs:
        if s.role in by_role:
            by_role[s.role].append(s)
    data = {role: _mean_by_month(rows) for role, rows in by_role.items()}

    months = sorted(set(data["intern"]) | set(data["mentor"]))
    out: list[dict] = []

    # 1. Низкие оценки / 2. Падение к прошлому циклу.
    for role in ("intern", "mentor"):
        for month in sorted(data[role]):
            cur = data[role][month]
            prev = data[role].get(month - 1, {})
            lows = [(k, v) for k, v in cur.items() if v <= th.low_rating_max]
            if lows:
                key, value = min(lows, key=lambda kv: kv[1])
                out.append(_signal(
                    "low_rating",
                    "high" if value <= th.low_rating_high else "medium",
                    month,
                    "Низкая оценка",
                    f"{WHO[role]} оценил(а) «{labels.get(key, key)}» в {value:g} (цикл {month}).",
                    role=role,
                    question_key=key,
                    intern_id=intern_id,
                ))
            for key, value in cur.items():
                if key not in prev:
                    continue
                drop = prev[key] - value
                if drop >= th.drop_min:
                    out.append(_signal(
                        "rating_drop",
                        "high" if drop >= th.drop_high else "medium",
                        month,
                        "Резкое падение оценки",
                        f"{WHO[role]}: «{labels.get(key, key)}» упало с {prev[key]:g} "
                        f"до {value:g} (−{drop:g}) к циклу {month}.",
                        role=role,
                        question_key=key,
                        intern_id=intern_id,
                    ))

    # 3. Расхождение оценок по явно настроенным парам каталога.
    for pair in pairs:
        for month in months:
            tv = data["intern"].get(month, {}).get(pair.intern_question)
            mv = data["mentor"].get(month, {}).get(pair.mentor_question)
            if tv is None or mv is None:
                continue
            diff = abs(tv - mv)
            if diff < th.divergence_min:
                continue
            out.append(_signal(
                "divergence",
                "high" if diff >= th.divergence_high else "medium",
                month,
                "Расхождение оценок стажёра и наставника",
                f"Цикл {month}: стажёр — «{labels.get(pair.intern_question, pair.intern_question)}» "
                f"= {tv:g}, наставник — «{labels.get(pair.mentor_question, pair.mentor_question)}» "
                f"= {mv:g} (разница {diff:g}).",
                intern_id=intern_id,
            ))

    # 4. Нисходящий тренд средней самооценки.
    intern_months = sorted(data["intern"])
    for month in intern_months:
        window = [month - th.trend_months + 1 + i for i in range(th.trend_months)]
        if window[0] < 1:
            continue
        avgs = []
        for m in window:
            values = list(data["intern"].get(m, {}).values())
            avgs.append(round(sum(values) / len(values), 2) if values else None)
        if all(a is not None for a in avgs) and all(
            avgs[i] > avgs[i + 1] for i in range(len(avgs) - 1)
        ):
            out.append(_signal(
                "downward_trend",
                "medium",
                month,
                "Нисходящий тренд",
                "Средняя самооценка снижается "
                f"{th.trend_months} цикла подряд: "
                + " → ".join(f"{a:.1f}" for a in avgs) + ".",
                intern_id=intern_id,
            ))

    return out


def compute_signals(
    db: Session,
    from_month: int = 1,
    to_month: int = 6,
    intern_id: int | None = None,
    thresholds: Thresholds | None = None,
    insights: Iterable[dict] | None = None,
) -> list[dict]:
    """Сигналы по срезу. `intern_id` — внутренний PK (для API резолвится из opaque_id).

    `insights` — уже посчитанные результаты AI-анализа комментариев (словари с
    полями internId/month/role/sentiment_score/risk_level/summary/issues).
    """
    th = thresholds or Thresholds()
    labels = _labels(db)
    pairs = list(db.scalars(select(ComparisonPair)))

    query = select(Submission).where(
        Submission.cycle >= from_month, Submission.cycle <= to_month
    )
    if intern_id is not None:
        query = query.where(Submission.about_intern_id == intern_id)
    subs = list(db.scalars(query.order_by(Submission.cycle)))

    grouped: dict[int | None, list[Submission]] = {}
    for s in subs:
        grouped.setdefault(s.about_intern_id, []).append(s)

    out: list[dict] = []
    for group_key, group in grouped.items():
        if group_key is None:
            continue  # без подтверждённой связи «ответ → человек» персональные сигналы не строим
        out.extend(_signals_for_intern(db, group, labels, pairs, th))

    # AI-сигналы: только по переданным результатам (без собственного хранилища).
    for item in insights or []:
        item_intern = item.get("internId")
        if intern_id is not None and item_intern is not None and item_intern != intern_id:
            continue
        month = item.get("month")
        score = item.get("sentiment_score")
        risk = item.get("risk_level")
        severity = None
        if risk == "high" or (isinstance(score, (int, float)) and score <= -0.6):
            severity = "high"
        elif risk == "medium" or (isinstance(score, (int, float)) and score <= -0.3):
            severity = "medium"
        if not severity or month is None:
            continue
        issues = ", ".join(item.get("issues") or []) or "—"
        role = item.get("role")
        out.append(_signal(
            "negative_comment",
            severity,
            int(month),
            "Негатив в комментариях",
            f"AI-анализ комментария ({WHO.get(role, role or 'участник').lower()}), "
            f"цикл {month}: {item.get('summary') or item.get('sentiment_label') or '—'}. "
            f"Проблемы: {issues}.",
            source="ai",
            role=role,
            intern_id=item_intern,
        ))

    return sorted_signals(out)


def sorted_signals(signals: list[dict]) -> list[dict]:
    """Сортировка: сначала high, затем цикл по убыванию, затем тип."""
    return sorted(
        signals,
        key=lambda s: (SEVERITY_RANK.get(s.get("severity"), 9), -int(s.get("month") or 0), s.get("type", "")),
    )


def compute_all(db: Session, from_month: int = 1, to_month: int = 6, **kwargs) -> list[dict]:
    """Сигналы по всем стажёрам (для отчёта/диагностики, без записи в БД)."""
    signals: list[dict] = []
    for intern in db.scalars(select(Intern).order_by(Intern.id)):
        signals.extend(compute_signals(db, from_month, to_month, intern_id=intern.id, **kwargs))
    return sorted_signals(signals)
