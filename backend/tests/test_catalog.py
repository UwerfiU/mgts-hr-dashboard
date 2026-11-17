"""WP1: каталог — загрузка из YAML, идемпотентность, валидация, доступ."""
import copy
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from app.catalog import access
from app.catalog.loader import CatalogConfigError, load_catalog
from app.config import settings
from app.db.models import ComparisonPair, Metric, Question


def _default_data() -> dict:
    return yaml.safe_load(Path(settings.catalog_path).read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "catalog.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_load_idempotent(catalog_db):
    r1 = load_catalog(catalog_db)
    r2 = load_catalog(catalog_db)
    assert r1.questions == r2.questions > 0
    assert r1.metrics == r2.metrics > 0
    db_count = catalog_db.scalar(select(func.count(Question.id)))
    assert db_count == r2.questions


def test_add_question(tmp_path, catalog_db):
    data = _default_data()
    data["questions"].append({
        "key": "wellbeing",
        "questionnaire": "intern_v1",
        "label": "Эмоциональное состояние",
        "type": "score",
        "scale_min": 1,
        "scale_max": 5,
    })
    r = load_catalog(catalog_db, _write(tmp_path, data))
    assert r.questions == len(_default_data()["questions"]) + 1
    q = access.get_question(catalog_db, "wellbeing")
    assert q is not None and q.label == "Эмоциональное состояние"
    assert access.get_scale(catalog_db, "wellbeing") == (1, 5)


def test_rename_label(tmp_path, catalog_db):
    """Переименование вопроса через конфиг — без изменения таблиц и схемы API."""
    data = _default_data()
    for q in data["questions"]:
        if q["key"] == "motivation":
            q["label"] = "Вовлечённость в программу"
    r = load_catalog(catalog_db, _write(tmp_path, data))
    assert r.removed == []  # вопрос не удалён, только переименован
    q = access.get_question(catalog_db, "motivation")
    assert q.label == "Вовлечённость в программу"


def test_stale_entries_removed(tmp_path, catalog_db):
    """Удалённые из конфига вопросы/метрики убираются из БД."""
    data = _default_data()
    data["questions"] = [q for q in data["questions"] if q["key"] != "readiness"]
    data["metrics"] = [m for m in data["metrics"] if m["id"] != "readiness"]
    r = load_catalog(catalog_db, _write(tmp_path, data))
    assert "question:readiness" in r.removed
    assert "metric:readiness" in r.removed
    assert access.get_question(catalog_db, "readiness") is None
    assert access.get_metric(catalog_db, "readiness") is None


def test_invalid_unknown_questionnaire(tmp_path, catalog_db):
    data = _default_data()
    data["questions"].append({"key": "x1", "questionnaire": "ghost_v1", "type": "score",
                              "scale_min": 1, "scale_max": 5})
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    assert "ghost_v1" in str(e.value)


def test_invalid_duplicate_key(tmp_path, catalog_db):
    data = copy.deepcopy(_default_data())
    dup = dict(data["questions"][0])
    data["questions"].append(dup)  # дубликат первого вопроса
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    assert "дублирует" in str(e.value)


def test_invalid_scale(tmp_path, catalog_db):
    data = _default_data()
    for q in data["questions"]:
        if q["key"] == "satisfaction":
            q["scale_min"], q["scale_max"] = 5, 1
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    assert "scale_min" in str(e.value)


def test_invalid_metric_role_mismatch(tmp_path, catalog_db):
    """Метрика роли intern не может ссылаться на вопрос анкеты наставника."""
    data = _default_data()
    data["metrics"].append({"id": "broken", "role": "intern",
                            "question_keys": ["skill_growth_mentor"]})
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    assert "метрика объявлена для роли" in str(e.value)


def test_invalid_comparison_direction_and_rule(tmp_path, catalog_db):
    data = _default_data()
    pair = data["comparison_pairs"][0]
    pair["direction"] = "sideways"
    pair["rule"] = "made_up"
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    msg = str(e.value)
    assert "direction" in msg and "rule" in msg


def test_invalid_version(tmp_path, catalog_db):
    data = _default_data()
    data["questionnaires"][0]["version"] = 0
    with pytest.raises(CatalogConfigError) as e:
        load_catalog(catalog_db, _write(tmp_path, data))
    assert "version" in str(e.value)


def test_access_helpers(catalog_db):
    intern_qs = access.get_questions(catalog_db, role="intern")
    mentor_qs = access.get_questions(catalog_db, role="mentor")
    # по 6 вопросов: 5 оценок + текстовый комментарий
    assert len(intern_qs) == 6 and len(mentor_qs) == 6

    metric = access.get_metric(catalog_db, "satisfaction")
    assert metric is not None and metric.role == "intern"
    qs = access.metric_questions(catalog_db, metric)
    assert [q.key for q in qs] == ["satisfaction"]

    pairs = access.get_comparison_pairs(catalog_db)
    assert len(pairs) == 1
    p: ComparisonPair = pairs[0]
    assert p.intern_question == "skill_growth"
    assert p.mentor_question == "skill_growth_mentor"
