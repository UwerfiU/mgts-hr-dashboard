"""WP8: сигналы — импортируемость и базовые правила поверх Submission/Answer."""
from sqlalchemy import select

from app.analytics import signals
from app.db.models import Intern
from app.normalization.core import normalize_and_store
from app.normalization.spec import SourceSpec
from app.sources.base import RawRecord

INTERN_SPEC = SourceSpec(
    source="form", role="intern", questionnaire="intern_v1", cycle_field="month",
    field_map={"q_skill": "skill_growth"}, about_intern_field="who",
)
MENTOR_SPEC = SourceSpec(
    source="form", role="mentor", questionnaire="mentor_v1", cycle_field="month",
    field_map={"q_skill": "skill_growth_mentor"},
    about_intern_field="who", author_mentor_field="mentor",
)


def _intern(db, alias: str) -> Intern:
    return db.scalar(select(Intern).where(Intern.alias == alias))


def test_module_imports_and_returns_list(catalog_db):
    assert callable(signals.compute_signals)
    assert isinstance(signals.compute_signals(catalog_db, 6, 6), list)


def test_low_rating_drop_and_divergence(catalog_db):
    normalize_and_store(catalog_db, [
        RawRecord("form", "sig:i1", {"month": 1, "who": "Сигнал Анна", "q_skill": 5}),
        RawRecord("form", "sig:i2", {"month": 2, "who": "Сигнал Анна", "q_skill": 2}),
    ], INTERN_SPEC)
    normalize_and_store(catalog_db, [
        RawRecord("form", "sig:m1", {"month": 2, "who": "Сигнал Анна",
                                     "mentor": "Сигнал Наставник", "q_skill": 5}),
    ], MENTOR_SPEC)

    intern = _intern(catalog_db, "Сигнал Анна")
    found = signals.compute_signals(catalog_db, 1, 6, intern_id=intern.id)
    types = {s["type"] for s in found}
    assert {"low_rating", "rating_drop", "divergence"} <= types
    assert all(s["internId"] == intern.id for s in found)
    # сортировка: high раньше medium
    ranks = [signals.SEVERITY_RANK[s["severity"]] for s in found]
    assert ranks == sorted(ranks)


def test_ai_insight_signal(catalog_db):
    normalize_and_store(catalog_db, [
        RawRecord("form", "sig:ai", {"month": 3, "who": "Сигнал Борис", "q_skill": 4}),
    ], INTERN_SPEC)
    intern = _intern(catalog_db, "Сигнал Борис")
    found = signals.compute_signals(
        catalog_db, 1, 6, intern_id=intern.id,
        insights=[{"internId": intern.id, "month": 3, "role": "intern",
                   "sentiment_score": -0.8, "risk_level": "high",
                   "summary": "Выгорание", "issues": ["перегрузка"]}],
    )
    ai = [s for s in found if s["source"] == "ai"]
    assert len(ai) == 1
    assert ai[0]["type"] == "negative_comment" and ai[0]["severity"] == "high"
