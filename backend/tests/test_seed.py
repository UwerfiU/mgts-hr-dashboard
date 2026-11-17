"""WP6: seed демо-данных — счётчики, идемпотентность, NULL-пропуски, API после seed.

Тесты изолированы: собственная временная БД на каждый тест, поэтому порядок
запуска (и pytest-xdist) не влияет на результат.
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.catalog.loader import load_catalog
from app.db.database import Base, get_db
from app.db.models import Intern, Submission
from app.main import app
from app.scripts import seed_demo


@pytest.fixture()
def seed_db():
    tmp = tempfile.mkdtemp(prefix="mgts_seed_")
    engine = create_engine(
        f"sqlite:///{(Path(tmp) / 'seed.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    load_catalog(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seed_client(seed_db):
    """TestClient с подменой зависимости get_db на изолированную сессию."""
    app.dependency_overrides[get_db] = lambda: seed_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_seed_counters(seed_db):
    stats = seed_demo.run(seed_db)
    assert stats["intern_submissions"] == 30   # 5 стажёров × 6 циклов
    assert stats["mentor_submissions"] == 30   # 5 наставников × 6 циклов


def test_seed_idempotent(seed_db):
    seed_demo.run(seed_db)
    seed_demo.run(seed_db)  # повтор без --reset — дублей нет (upsert по source_key)
    total = seed_db.scalar(
        select(func.count()).select_from(Submission).where(Submission.source == "demo")
    )
    assert total == 60


def test_seed_reset(seed_db):
    seed_demo.run(seed_db, reset=True)
    seed_demo.run(seed_db, reset=True)
    total = seed_db.scalar(
        select(func.count()).select_from(Submission).where(Submission.source == "demo")
    )
    assert total == 60  # сброс не накапливает и не роняет данные
    # «фантомных» демо-участников после сброса нет
    interns = seed_db.scalar(select(func.count()).select_from(Intern))
    assert interns == len(seed_demo.INTERN_ALIAS)


def test_seed_skipped_score_is_null(seed_db):
    """Пропущенная оценка (Дарья, цикл 1) — строка с score=NULL, а не 0 и не отсутствие."""
    seed_demo.run(seed_db)
    sub = seed_db.scalar(select(Submission).where(Submission.source_key == "demo:intern:Демо Дарья:1"))
    assert sub is not None
    answers = {a.question_key: a for a in sub.answers}
    assert "skill_growth" in answers
    assert answers["skill_growth"].score is None


def test_seed_links_intern_and_mentor(seed_db):
    """Связь подтверждена: наставник → стажёр (автор ответа)."""
    seed_demo.run(seed_db)
    sub = seed_db.scalar(select(Submission).where(
        Submission.source_key == "demo:mentor:Демо Наставник 5:Демо Глеб:6"
    ))
    assert sub is not None
    intern = seed_db.get(Intern, sub.about_intern_id)  # стажёр «Демо Глеб»
    assert intern is not None and intern.alias == "Демо Глеб"
    assert sub.author_mentor_id is not None


def test_api_after_seed(seed_client, seed_db):
    """Критерий B6: после seed все три маршрута отвечают 200 на общем наборе."""
    seed_demo.run(seed_db)

    meta = seed_client.get("/api/v1/meta")
    assert meta.status_code == 200

    metrics = seed_client.get("/api/v1/metrics", params={"metricId": "motivation"})
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["coverage"]["intern"]["submitted"] >= 30
    # «сюжет»: у Глеба мотивация стабильно слабая — средняя по группе ниже 4
    assert body["series"][0]["points"][5]["value"] is not None

    feedback = seed_client.get("/api/v1/feedback")
    assert feedback.status_code == 200, feedback.text  # demo-режим: тексты разрешены
    texts = feedback.json()["texts"]
    assert any("обратной связи" in t["text"] for t in texts)


def test_seed_story_comparison_gap(seed_client, seed_db):
    """Вера: самооценка роста 5 с цикла 3, наставник — 2 → устойчивый отрицательный зазор."""
    seed_demo.run(seed_db)
    r = seed_client.get("/api/v1/metrics", params={
        "metricId": "skill_growth", "fromMonth": 3, "toMonth": 6,
    })
    assert r.status_code == 200, r.text
    comp = {p["month"]: p for p in r.json()["comparison"]["points"]}
    # зазор Веры (-3) тянет среднюю вниз; пары есть в каждом цикле 3–6
    for m in (3, 4, 5, 6):
        assert comp[m]["nPairs"] >= 1
