"""WP2: нормализация — единый тип записи из разных форматов, валидация, отчёт, идемпотентность."""
from dataclasses import asdict

import pytest
from sqlalchemy import select

from app.db.models import Answer, Intern, Submission
from app.normalization.core import normalize_and_store, normalize_record, resolve_intern
from app.normalization.spec import SourceSpec
from app.sources.base import RawRecord


def _excel_spec() -> SourceSpec:
    return SourceSpec(
        source="excel",
        role="intern",
        questionnaire="intern_v1",
        cycle_field="month",
        field_map={
            "score_skill": "skill_growth",
            "score_tasks": "task_clarity",
            "score_mentor": "mentor_support",
            "score_motivation": "motivation",
            "score_overall": "satisfaction",
            "comment_text": "comment_intern",
        },
        about_intern_field="trainee_name",
    )


def _form_spec() -> SourceSpec:
    """Та же логика, другие имена полей — имитация другого формата (Forms API)."""
    return SourceSpec(
        source="form",
        role="intern",
        questionnaire="intern_v1",
        cycle_field="cycle",
        field_map={
            "q_skill": "skill_growth",
            "q_tasks": "task_clarity",
            "q_mentor": "mentor_support",
            "q_motivation": "motivation",
            "q_overall": "satisfaction",
            "q_comment": "comment_intern",
        },
        about_intern_field="intern_alias",
    )


def _excel_raw(key: str, **fields) -> RawRecord:
    return RawRecord(source="excel", source_key=key, payload={"month": 2, "trainee_name": "Стажёр Тест", **fields})


def test_valid_record_stored(catalog_db):
    r = normalize_and_store(
        catalog_db,
        [_excel_raw("n1:r1", score_skill=4, score_tasks="3.5", comment_text="Всё хорошо")],
        _excel_spec(),
    )
    assert r.accepted == 1 and r.created == 1 and not r.skipped

    sub = catalog_db.scalar(select(Submission).where(Submission.source_key == "n1:r1"))
    assert sub is not None and sub.cycle == 2 and sub.role == "intern"
    assert sub.about_intern_id is not None
    answers = {a.question_key: a for a in sub.answers}
    assert answers["skill_growth"].score == 4.0
    assert answers["task_clarity"].score == 3.5
    assert answers["comment_intern"].text == "Всё хорошо"


def test_empty_score_is_null_not_zero(catalog_db):
    r = normalize_and_store(
        catalog_db, [_excel_raw("n2:r1", score_skill="", score_tasks=None)], _excel_spec()
    )
    assert r.accepted == 1
    sub = catalog_db.scalar(select(Submission).where(Submission.source_key == "n2:r1"))
    answers = {a.question_key: a for a in sub.answers}
    assert answers["skill_growth"].score is None  # пропуск → NULL, не 0
    assert answers["task_clarity"].score is None


def test_out_of_scale_skipped(catalog_db):
    r = normalize_and_store(catalog_db, [_excel_raw("n3:r1", score_skill=7)], _excel_spec())
    assert r.accepted == 0 and len(r.skipped) == 1
    assert "шкалы" in r.skipped[0].reason


def test_non_numeric_score_skipped(catalog_db):
    r = normalize_and_store(catalog_db, [_excel_raw("n4:r1", score_skill="abc")], _excel_spec())
    assert r.accepted == 0 and len(r.skipped) == 1
    assert "не число" in r.skipped[0].reason


@pytest.mark.parametrize("bad_cycle", [0, 7, "x", None])
def test_bad_cycle_skipped(catalog_db, bad_cycle):
    if bad_cycle is None:
        raw = RawRecord(source="excel", source_key="n5:empty", payload={"trainee_name": "X"})
    else:
        raw = _excel_raw(f"n5:r{bad_cycle!r}", score_skill=4, month=bad_cycle)
    r = normalize_and_store(catalog_db, [raw], _excel_spec())
    assert r.accepted == 0 and len(r.skipped) == 1
    assert "цикл" in r.skipped[0].reason


def test_unknown_question_key_skipped(catalog_db):
    spec = _excel_spec().__class__(
        source="excel", role="intern", questionnaire="intern_v1", cycle_field="month",
        field_map={"weird": "no_such_question"}, about_intern_field="trainee_name",
    )
    r = normalize_and_store(catalog_db, [_excel_raw("n6:r1")], spec)
    assert r.accepted == 0 and len(r.skipped) == 1
    assert "не найден в каталоге" in r.skipped[0].reason


def test_two_formats_same_canonical(catalog_db):
    """Два разных входных формата дают одинаковый тип записи."""
    raw_excel = RawRecord(
        source="excel", source_key="n7:e1",
        payload={"month": 3, "trainee_name": "Анна", "score_skill": 4, "comment_text": "ok"},
    )
    raw_form = RawRecord(
        source="form", source_key="n7:f1",
        payload={"cycle": 3, "intern_alias": "Анна", "q_skill": 4, "q_comment": "ok"},
    )
    rec_excel, reasons_e = normalize_record(catalog_db, raw_excel, _excel_spec())
    rec_form, reasons_f = normalize_record(catalog_db, raw_form, _form_spec())
    assert not reasons_e and not reasons_f

    def core(rec):
        d = asdict(rec)
        d.pop("source"); d.pop("source_key")
        return d

    assert core(rec_excel) == core(rec_form)


def test_idempotent_upsert(catalog_db):
    spec = _excel_spec()
    r1 = normalize_and_store(catalog_db, [_excel_raw("n8:r1", score_skill=4)], spec)
    r2 = normalize_and_store(catalog_db, [_excel_raw("n8:r1", score_skill=2)], spec)
    assert (r1.created, r1.updated) == (1, 0)
    assert (r2.created, r2.updated) == (0, 1)

    subs = list(catalog_db.scalars(select(Submission).where(Submission.source_key == "n8:r1")))
    assert len(subs) == 1  # повтор не создаёт дубль
    answers = {a.question_key: a for a in subs[0].answers}
    assert answers["skill_growth"].score == 2  # значение обновлено


def test_about_intern_resolution(catalog_db):
    i1 = resolve_intern(catalog_db, "Смирнова Анна")
    i2 = resolve_intern(catalog_db, "Смирнова Анна")
    assert i1.id == i2.id
    assert i1.opaque_id.startswith("AUTO-")  # стабильный непрозрачный id

    r = normalize_and_store(
        catalog_db,
        [RawRecord(source="excel", source_key="n9:r1",
                   payload={"month": 2, "trainee_name": "Смирнова Анна", "score_skill": 4}),
         RawRecord(source="excel", source_key="n9:r2", payload={"month": 1})],  # без «о ком»
        _excel_spec(),
    )
    assert r.accepted == 2
    s1 = catalog_db.scalar(select(Submission).where(Submission.source_key == "n9:r1"))
    s2 = catalog_db.scalar(select(Submission).where(Submission.source_key == "n9:r2"))
    assert s1.about_intern_id == i1.id
    assert s2.about_intern_id is None  # ответ без связи хранится


def test_report_summary(catalog_db):
    r = normalize_and_store(
        catalog_db,
        [
            _excel_raw("n10:ok", score_skill=4),
            _excel_raw("n10:scale", score_skill=9),
            RawRecord(source="excel", source_key="n10:cyc", payload={"month": 99}),
        ],
        _excel_spec(),
    )
    assert (r.accepted, len(r.skipped)) == (1, 2)
    text = r.summary_text()
    assert "Принято: 1" in text
    assert "n10:scale" in text and "шкалы" in text
    assert r.ok


def test_empty_comment_no_answer(catalog_db):
    normalize_and_store(catalog_db, [_excel_raw("n11:r1", score_skill=4, comment_text="")], _excel_spec())
    sub = catalog_db.scalar(select(Submission).where(Submission.source_key == "n11:r1"))
    assert all(a.question_key != "comment_intern" for a in sub.answers)  # пустого комментария нет

    normalize_and_store(catalog_db, [_excel_raw("n11:r2", score_skill=4, comment_text="  нормальный месяц  ")], _excel_spec())
    sub2 = catalog_db.scalar(select(Submission).where(Submission.source_key == "n11:r2"))
    comment = next(a for a in sub2.answers if a.question_key == "comment_intern")
    assert comment.text == "нормальный месяц"  # обрезка пробелов
