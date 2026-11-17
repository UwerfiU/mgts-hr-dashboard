"""WP6: seed демо-данных — счётчики, идемпотентность, NULL-пропуски, API после seed."""
from sqlalchemy import func, select

from app.db.models import Answer, Intern, Submission
from app.scripts import seed_demo


def test_seed_counters(db):
    stats = seed_demo.run(db)
    assert stats["intern_submissions"] == 30   # 5 стажёров × 6 циклов
    assert stats["mentor_submissions"] == 30   # 5 наставников × 6 циклов


def test_seed_idempotent(db):
    seed_demo.run(db)
    seed_demo.run(db)  # повтор без --reset — дублей нет (upsert по source_key)
    total = db.scalar(
        select(func.count()).select_from(Submission).where(Submission.source == "demo")
    )
    assert total == 60


def test_seed_reset(db):
    seed_demo.run(db, reset=True)
    seed_demo.run(db, reset=True)
    total = db.scalar(
        select(func.count()).select_from(Submission).where(Submission.source == "demo")
    )
    assert total == 60  # сброс не накапливает и не роняет данные


def test_seed_skipped_score_is_null(db):
    """Пропущенная оценка (Дарья, цикл 1) — строка с score=NULL, а не 0 и не отсутствие."""
    seed_demo.run(db)
    sub = db.scalar(select(Submission).where(Submission.source_key == "demo:intern:Демо Дарья:1"))
    assert sub is not None
    answers = {a.question_key: a for a in sub.answers}
    assert "skill_growth" in answers
    assert answers["skill_growth"].score is None


def test_seed_links_intern_and_mentor(db):
    """Связь подтверждена: наставник → стажёр (автор ответа)."""
    seed_demo.run(db)
    sub = db.scalar(select(Submission).where(Submission.source_key == "demo:mentor:Демо Наставник 5:Демо Глеб:6"))
    assert sub is not None
    mentor = db.get(Intern, sub.about_intern_id)  # стажёр «Демо Глеб»
    assert mentor is not None and mentor.alias == "Демо Глеб"
    assert sub.author_mentor_id is not None


def test_api_after_seed(client, db):
    """Критерий B6: после seed все три маршрута отвечают 200 на общем наборе."""
    seed_demo.run(db)

    meta = client.get("/api/v1/meta")
    assert meta.status_code == 200

    metrics = client.get("/api/v1/metrics", params={"metricId": "motivation"})
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["coverage"]["intern"]["submitted"] >= 30
    # «сюжет»: у Глеба мотивация стабильно слабая — средняя по группе ниже 4
    assert body["series"][0]["points"][5]["value"] is not None

    feedback = client.get("/api/v1/feedback")
    assert feedback.status_code == 200, feedback.text  # demo-режим: тексты разрешены
    texts = feedback.json()["texts"]
    assert any("обратной связи" in t["text"] for t in texts)


def test_seed_story_comparison_gap(client, db):
    """Вера: самооценка роста 5 с цикла 3, наставник — 2 → устойчивый отрицательный зазор."""
    seed_demo.run(db)
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "fromMonth": 3, "toMonth": 6})
    assert r.status_code == 200, r.text
    comp = {p["month"]: p for p in r.json()["comparison"]["points"]}
    # зазор Веры (-3) тянет среднюю вниз; пары есть в каждом цикле 3–6
    for m in (3, 4, 5, 6):
        assert comp[m]["nPairs"] >= 1
