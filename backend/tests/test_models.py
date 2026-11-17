"""WP1: модель данных — идемпотентность, опциональная связь «о ком», NULL-оценки.

Внимание: тесты разделяют одну БД (session-scoped), поэтому каждый тест
использует УНИКАЛЬНЫЕ source_key — иначе упрёмся в uq_submission соседних тестов.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Answer, Intern, Submission


def _submission(db, source_key: str, about_intern_id=None) -> Submission:
    s = Submission(
        source="form",
        source_key=source_key,
        questionnaire="intern_v1",
        cycle=1,
        role="intern",
        about_intern_id=about_intern_id,
    )
    db.add(s)
    return s


def test_submission_without_intern_and_null_score(db):
    """Ответ без связи со стажёром хранится; пропуск оценки = NULL, не 0."""
    s = _submission(db, "form:m1:r1")
    db.flush()  # получить id отправки
    a = Answer(submission_id=s.id, question_key="skill_growth", score=None, text="пока нет мнения")
    db.add(a)
    db.commit()

    got = db.get(Submission, s.id)
    assert got.about_intern_id is None
    answers = list(got.answers)
    assert len(answers) == 1
    assert answers[0].score is None


def test_submission_source_key_unique(db):
    """Уникальность (source, source_key) — основа идемпотентности."""
    _submission(db, "form:m2:r1")
    _submission(db, "form:m2:r1")
    with pytest.raises(IntegrityError):
        db.flush()


def test_submission_same_key_different_source_ok(db):
    """Один и тот же ключ в РАЗНЫХ источниках — допустимо (это разные записи)."""
    s1 = _submission(db, "form:m3:r1")
    s2 = Submission(source="excel", source_key="m3:r1", questionnaire="intern_v1", cycle=1, role="intern")
    db.add(s2)
    db.commit()
    assert s1.id != s2.id


def test_answer_unique_per_submission(db):
    """Один ответ на (отправка, вопрос)."""
    s = _submission(db, "form:m4:r1")
    db.flush()
    db.add(Answer(submission_id=s.id, question_key="skill_growth", score=4))
    db.add(Answer(submission_id=s.id, question_key="skill_growth", score=3))
    with pytest.raises(IntegrityError):
        db.flush()


def test_intern_opaque_id_unique(db):
    db.add(Intern(opaque_id="I-001", alias="Стажёр 1"))
    db.add(Intern(opaque_id="I-001", alias="Дубль"))
    with pytest.raises(IntegrityError):
        db.flush()
