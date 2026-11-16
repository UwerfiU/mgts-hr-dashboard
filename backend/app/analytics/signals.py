# =============================================================================
# STAGE 2 / WP8 — основа из начального скелета. Не подключена к API.
# После WP1 (нормализованная модель данных) адаптировать:
#   * импорт PAIRED_QUESTIONS/label → app/catalog (конфиг catalog.yaml);
#   * ORM-модели Response/CommentInsight → Submission/Answer + результаты AI.
# =============================================================================

"""Генерация сигналов о проблемах: детерминированные правила + AI-сигналы.

Правила (source="rule"):
  * low_rating      — оценка ≤ 2 (в любой из форм)
  * rating_drop     — падение оценки ≥ 2 балла к прошлому месяцу
  * divergence      — расхождение оценок стажёра и наставника по парным вопросам
  * downward_trend  — средняя самооценка снижается 3 месяца подряд

AI (source="ai"):
  * negative_comment — негативный sentiment / высокий риск по результату анализа комментария

Пересчёт идемпотентен: существующие сигналы стажёра удаляются и создаются заново.
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import CommentInsight, Response, Signal, Trainee
from .survey_schema import PAIRED_QUESTIONS, label

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

WHO = {"trainee": "Стажёр", "mentor": "Наставник"}


def _avg(values) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


def _sig(trainee_id: int, month: int, type_: str, severity: str, title: str, reason: str, source: str = "rule") -> Signal:
    return Signal(
        trainee_id=trainee_id,
        month=month,
        type=type_,
        severity=severity,
        title=title,
        reason=reason,
        source=source,
    )


def _month_matrix(responses: list[Response]) -> dict[str, dict[int, dict]]:
    """{form: {month: {question_key: value}}}."""
    data: dict[str, dict[int, dict]] = {"trainee": {}, "mentor": {}}
    for r in responses:
        data[r.respondent_type].setdefault(r.month, {}).update(r.ratings or {})
    return data


def recompute_for_trainee(db: Session, trainee_id: int) -> None:
    db.execute(delete(Signal).where(Signal.trainee_id == trainee_id))

    responses = list(
        db.scalars(select(Response).where(Response.trainee_id == trainee_id).order_by(Response.month)).all()
    )
    if not responses:
        db.commit()
        return

    insights: dict[int, CommentInsight] = {}
    for r in responses:
        i = db.scalar(select(CommentInsight).where(CommentInsight.response_id == r.id))
        if i is not None:
            insights[r.id] = i

    data = _month_matrix(responses)
    months = sorted(set(data["trainee"]) | set(data["mentor"]))
    new_signals: list[Signal] = []

    for m in months:
        t, mo = data["trainee"].get(m, {}), data["mentor"].get(m, {})
        pt, pm = data["trainee"].get(m - 1, {}), data["mentor"].get(m - 1, {})

        # 1. Низкие оценки
        for form, vals in (("trainee", t), ("mentor", mo)):
            lows = [(k, v) for k, v in vals.items() if v <= 2]
            if lows:
                k, v = min(lows, key=lambda kv: kv[1])
                sev = "high" if v <= 1 else "medium"
                new_signals.append(_sig(
                    trainee_id, m, "low_rating", sev, "Низкая оценка",
                    f"{WHO[form]} оценил(а) «{label(form, k)}» в {v:g} из 5 (месяц {m}).",
                ))

        # 2. Резкое падение оценки к прошлому месяцу
        for form, prev, cur in (("trainee", pt, t), ("mentor", pm, mo)):
            for k, v in cur.items():
                if k in prev:
                    drop = prev[k] - v
                    if drop >= 2:
                        new_signals.append(_sig(
                            trainee_id, m, "rating_drop", "high" if drop >= 3 else "medium",
                            "Резкое падение оценки",
                            f"{WHO[form]}: «{label(form, k)}» упало с {prev[k]:g} до {v:g} (−{drop:g}) к месяцу {m}.",
                        ))

        # 3. Расхождение оценок стажёра и наставника
        for tk, mk in PAIRED_QUESTIONS.items():
            if tk in t and mk in mo:
                diff = abs(t[tk] - mo[mk])
                if diff >= 2:
                    new_signals.append(_sig(
                        trainee_id, m, "divergence", "high" if diff >= 3 else "medium",
                        "Расхождение оценок стажёра и наставника",
                        f"Месяц {m}: стажёр — «{label('trainee', tk)}» = {t[tk]:g}, "
                        f"наставник — «{label('mentor', mk)}» = {mo[mk]:g} (разница {diff:g}).",
                    ))

        # 4. Нисходящий тренд самооценки (3 месяца подряд)
        if m >= 3:
            avgs = [_avg(data["trainee"].get(x, {}).values()) for x in (m - 2, m - 1, m)]
            if all(a is not None for a in avgs) and avgs[0] > avgs[1] > avgs[2]:
                new_signals.append(_sig(
                    trainee_id, m, "downward_trend", "medium", "Нисходящий тренд",
                    f"Средняя самооценка снижается три месяца подряд: "
                    f"{avgs[0]:.1f} → {avgs[1]:.1f} → {avgs[2]:.1f}.",
                ))

        # 5. Негатив в комментариях (по AI-инсайтам)
        for r in responses:
            if r.month != m:
                continue
            i = insights.get(r.id)
            if i is None or i.provider == "none":
                continue
            sev = None
            if i.risk_level == "high" or i.sentiment_score <= -0.6:
                sev = "high"
            elif i.risk_level == "medium" or i.sentiment_score <= -0.3:
                sev = "medium"
            if sev:
                issues = ", ".join(i.issues) if i.issues else "—"
                new_signals.append(_sig(
                    trainee_id, m, "negative_comment", sev, "Негатив в комментариях",
                    f"AI-анализ комментария ({WHO[r.respondent_type].lower()}), месяц {m}: "
                    f"{i.summary or i.sentiment_label}. Проблемы: {issues}.",
                    source="ai",
                ))

    db.add_all(new_signals)
    db.commit()


def recompute_all(db: Session) -> int:
    """Полный пересчёт сигналов по всем стажёрам. Возвращает общее число сигналов."""
    for t in db.scalars(select(Trainee)).all():
        recompute_for_trainee(db, t.id)
    return len(list(db.scalars(select(Signal))))


def sorted_signals(signals: list[Signal]) -> list[Signal]:
    """Сортировка: сначала high, потом месяц по убыванию."""
    return sorted(signals, key=lambda s: (SEVERITY_RANK.get(s.severity, 9), -s.month, s.id))
