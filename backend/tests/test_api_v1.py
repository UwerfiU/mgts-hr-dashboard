"""WP5: API /api/v1 — контракт, права на детализацию, фикстуры.

Стратегия данных (общая БД в рамках сессии):
  * персональные срезы проверяем по УНИКАЛЬНЫМ псевдонимам «API ...» — их данные точные;
  * глобальные проверки опираемся на месяц 6, который гарантированно пуст
    (остальные тесты пишут циклы 1–3), и на структуру ответа.
"""
import json

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import Intern, Mentor
from app.normalization.core import normalize_and_store
from app.normalization.spec import SourceSpec
from app.sources.base import RawRecord

INTERN_SPEC = SourceSpec(
    source="form", role="intern", questionnaire="intern_v1", cycle_field="month",
    field_map={"score_skill": "skill_growth", "comment_text": "comment_intern"},
    about_intern_field="trainee_name",
)
MENTOR_SPEC = SourceSpec(
    source="form", role="mentor", questionnaire="mentor_v1", cycle_field="month",
    field_map={"score_skill_m": "skill_growth_mentor"},
    about_intern_field="intern_name", author_mentor_field="mentor_name",
)


def _seed(db):
    """Синтетика: 2 стажёра, 2 наставника, циклы 1–3. Идемпотентно (upsert по source_key)."""
    intern_records = [
        RawRecord("form", "api:a1", {"month": 1, "trainee_name": "API Анна", "score_skill": 4,
                                     "comment_text": "API тестовый комментарий"}),
        RawRecord("form", "api:a2", {"month": 2, "trainee_name": "API Анна", "score_skill": 5}),
        RawRecord("form", "api:a3", {"month": 3, "trainee_name": "API Анна", "score_skill": 2}),
        RawRecord("form", "api:b1", {"month": 1, "trainee_name": "API Борис", "score_skill": 3}),
        RawRecord("form", "api:b2", {"month": 2, "trainee_name": "API Борис", "score_skill": 3}),
    ]
    mentor_records = [
        RawRecord("form", "api:m1", {"month": 1, "intern_name": "API Анна", "mentor_name": "API Наставник", "score_skill_m": 3}),
        RawRecord("form", "api:m2", {"month": 2, "intern_name": "API Анна", "mentor_name": "API Наставник", "score_skill_m": 4}),
        RawRecord("form", "api:m3", {"month": 1, "intern_name": "API Борис", "mentor_name": "API Наставник", "score_skill_m": 3}),
        RawRecord("form", "api:m4", {"month": 1, "intern_name": "API Борис", "mentor_name": "API Второй", "score_skill_m": 2}),
    ]
    normalize_and_store(db, intern_records, INTERN_SPEC)
    normalize_and_store(db, mentor_records, MENTOR_SPEC)

    ids = {
        "anna": db.scalar(select(Intern.opaque_id).where(Intern.alias == "API Анна")),
        "boris": db.scalar(select(Intern.opaque_id).where(Intern.alias == "API Борис")),
        "mentor1": db.scalar(select(Mentor.opaque_id).where(Mentor.alias == "API Наставник")),
        "mentor2": db.scalar(select(Mentor.opaque_id).where(Mentor.alias == "API Второй")),
    }
    assert all(ids.values()), "сид-данные не созданы"
    return ids


@pytest.fixture()
def seeded(db):
    _seed(db)
    return db


@pytest.fixture()
def allow_numeric(tmp_path, monkeypatch):
    """Политика с разрешёнными персональными срезами (числовая история)."""
    p = tmp_path / "permissions.yaml"
    p.write_text(
        "personal_slices_allowed: true\nnumeric_history_allowed: true\ntext_display_allowed: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "permissions_path", str(p))


@pytest.fixture()
def allow_texts(tmp_path, monkeypatch):
    p = tmp_path / "permissions.yaml"
    p.write_text(
        "personal_slices_allowed: false\nnumeric_history_allowed: false\ntext_display_allowed: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "permissions_path", str(p))


@pytest.fixture()
def allow_personal_texts(tmp_path, monkeypatch):
    """Личная связь и тексты разрешены, числовая история — нет (флаги независимы)."""
    p = tmp_path / "permissions.yaml"
    p.write_text(
        "personal_slices_allowed: true\nnumeric_history_allowed: false\ntext_display_allowed: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "permissions_path", str(p))


# --- /meta --------------------------------------------------------------------

def test_meta_ok(client):
    r = client.get("/api/v1/meta")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataMode"] == "demo"
    assert body["cycles"] == [1, 2, 3, 4, 5, 6]
    metric = next(m for m in body["metrics"] if m["metricId"] == "skill_growth")
    assert metric["role"] == "intern" and metric["scale"] == {"min": 1, "max": 5}
    assert any(c["id"] == "comment_intern" for c in body["categories"])
    assert body["detailPermissions"]["personalSlicesAllowed"] is False
    assert isinstance(body["sync"], list)


# --- /metrics -----------------------------------------------------------------

def test_metrics_global_empty_month(client, seeded):
    """Месяц 6 гарантированно пуст: точные нули и null вместо 0."""
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "fromMonth": 6, "toMonth": 6})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coverage"]["intern"] == {"submitted": 0, "expected": 5}
    assert body["coverage"]["mentor"] == {"submitted": 0, "expected": 5}
    point = body["series"][0]["points"][0]
    assert point == {"month": 6, "value": None, "n": 0}  # null, не 0
    assert body["comparison"]["status"] == "unavailable"
    assert len(body["series"]) == 2  # своя роль + роль-партнёр по паре сравнения


def test_metrics_unknown_metric(client):
    r = client.get("/api/v1/metrics", params={"metricId": "nope"})
    assert r.status_code == 404
    assert r.json()["code"] == "METRIC_NOT_FOUND"


def test_metrics_bad_range(client):
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "fromMonth": 3, "toMonth": 1})
    assert r.status_code == 422
    assert r.json()["code"] == "BAD_MONTH_RANGE"


def test_meta_aliases_include_opaque_ids(client, seeded, allow_numeric):
    """aliases отдаются парами {id, alias}; id — именно opaque_id (его принимают фильтры)."""
    ids = _seed(seeded)
    body = client.get("/api/v1/meta").json()
    assert body["aliases"]["allowed"] is True
    anna = next(a for a in body["aliases"]["interns"] if a["alias"] == "API Анна")
    assert anna == {"id": ids["anna"], "alias": "API Анна"}
    assert all(set(a) == {"id", "alias"} for a in body["aliases"]["mentors"])


def test_metrics_personal_forbidden_by_default(client, seeded):
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "internId": "1"})
    assert r.status_code == 403
    assert r.json()["code"] == "PERSONAL_SLICE_NOT_ALLOWED"


def test_metrics_both_filters_rejected(client, seeded, allow_numeric):
    ids = _seed(seeded)
    r = client.get("/api/v1/metrics", params={
        "metricId": "skill_growth", "internId": ids["anna"], "mentorId": ids["mentor1"],
    })
    assert r.status_code == 422
    assert r.json()["code"] == "ONE_FILTER_ONLY"


def test_metrics_unknown_person(client, seeded, allow_numeric):
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "internId": "NO-SUCH-ID"})
    assert r.status_code == 404
    assert r.json()["code"] == "PERSON_NOT_FOUND"


def test_metrics_pk_is_not_opaque_id(client, seeded, allow_numeric):
    """Внутренний PK не должен приниматься как идентификатор участника."""
    anna_pk = seeded.scalar(select(Intern.id).where(Intern.alias == "API Анна"))
    r = client.get("/api/v1/metrics", params={"metricId": "skill_growth", "internId": str(anna_pk)})
    assert r.status_code == 404
    assert r.json()["code"] == "PERSON_NOT_FOUND"



def test_metrics_personal_slice(client, seeded, allow_numeric):
    ids = _seed(seeded)
    r = client.get("/api/v1/metrics", params={
        "metricId": "skill_growth", "fromMonth": 1, "toMonth": 3, "internId": str(ids["anna"]),
    })
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["coverage"]["intern"]["submitted"] == 3
    assert body["coverage"]["intern"]["expected"] is None  # персональный план не моделируется

    points = {p["month"]: p for p in body["series"][0]["points"]}
    assert points[1] == {"month": 1, "value": 4.0, "n": 1}
    assert points[2] == {"month": 2, "value": 5.0, "n": 1}
    assert points[3] == {"month": 3, "value": 2.0, "n": 1}

    comp = {p["month"]: p for p in body["comparison"]["points"]}
    assert body["comparison"]["status"] == "available"
    assert body["comparison"]["direction"] == "intern_minus_mentor"
    assert comp[1] == {"month": 1, "value": 1.0, "nPairs": 1}   # 4 - 3
    assert comp[2] == {"month": 2, "value": 1.0, "nPairs": 1}   # 5 - 4
    assert comp[3]["value"] is None and comp[3]["nPairs"] == 0


def test_metrics_mentor_filter(client, seeded, allow_numeric):
    """Фильтр по наставнику: только его связанные пары; чужие ответы не учитываются."""
    ids = _seed(seeded)
    r = client.get("/api/v1/metrics", params={
        "metricId": "skill_growth", "fromMonth": 1, "toMonth": 3, "mentorId": str(ids["mentor1"]),
    })
    assert r.status_code == 200, r.text
    comp = {p["month"]: p for p in r.json()["comparison"]["points"]}
    # m1: Анна (4-3) и Борис (3-3) — ответ «API Второй» о Боре исключён (не автор)
    assert comp[1] == {"month": 1, "value": 0.5, "nPairs": 2}
    # m2: только Анна (5-4); у наставника по Бору ответа за m2 нет
    assert comp[2] == {"month": 2, "value": 1.0, "nPairs": 1}


# --- /feedback ----------------------------------------------------------------

def test_feedback_forbidden_by_default(client, seeded, monkeypatch):
    # запрет текстов проверяем в real-режиме (в demo показ синтетики разрешён)
    monkeypatch.setattr(settings, "data_mode", "real")
    r = client.get("/api/v1/feedback", params={"fromMonth": 1, "toMonth": 3})
    assert r.status_code == 403
    assert r.json()["code"] == "TEXTS_NOT_ALLOWED"


def test_feedback_allowed(client, seeded, allow_texts):
    r = client.get("/api/v1/feedback", params={"fromMonth": 1, "toMonth": 3})
    assert r.status_code == 200, r.text
    texts = r.json()["texts"]
    mine = [t for t in texts if t["text"] == "API тестовый комментарий"]
    assert len(mine) == 1
    assert mine[0]["month"] == 1 and mine[0]["role"] == "intern"
    assert mine[0]["questionKey"] == "comment_intern"
    # в ответе нет идентификаторов авторов (анонимность при малой выборке)
    for t in texts:
        assert set(t) == {"month", "role", "questionKey", "text"}

    r2 = client.get("/api/v1/feedback", params={"fromMonth": 1, "toMonth": 3, "categoryId": "comment_mentor"})
    assert all(t["questionKey"] == "comment_mentor" for t in r2.json()["texts"])

    # пустой срез — 200 + [] (различается с запретом)
    r3 = client.get("/api/v1/feedback", params={"fromMonth": 6, "toMonth": 6})
    assert r3.status_code == 200 and r3.json() == {"texts": []}


def test_feedback_unknown_person(client, seeded, allow_personal_texts):
    r = client.get("/api/v1/feedback", params={"internId": "NO-SUCH-ID"})
    assert r.status_code == 404
    assert r.json()["code"] == "PERSON_NOT_FOUND"


def test_feedback_personal_filter_does_not_require_numeric(client, seeded, allow_personal_texts):
    """Тексты и числовая история — независимые флаги: numeric_history_allowed=false не мешает."""
    ids = _seed(seeded)
    r = client.get("/api/v1/feedback", params={"internId": ids["anna"], "fromMonth": 1, "toMonth": 3})
    assert r.status_code == 200, r.text
    texts = r.json()["texts"]
    assert [t["text"] for t in texts] == ["API тестовый комментарий"]


# --- фикстуры контракта --------------------------------------------------------

def test_fixtures_contract():
    import pathlib

    root = pathlib.Path(__file__).parent.parent / "fixtures"
    files = sorted(root.rglob("*.json"))
    assert len(files) >= 9

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if f.parent.name == "meta":
            assert {"dataMode", "cycles", "metrics", "detailPermissions", "sync"} <= set(data)
        elif f.parent.name == "metrics" and "code" not in data:
            assert {"coverage", "series", "distribution", "comparison"} <= set(data)
            for s in data["series"]:
                for p in s["points"]:
                    assert p["value"] is None or isinstance(p["value"], (int, float))
        elif f.parent.name == "feedback" and "code" not in data:
            for t in data["texts"]:
                assert set(t) == {"month", "role", "questionKey", "text"}
        else:
            assert {"code", "message"} <= set(data)
