"""WP4: коннектор форм — синхронизация, идемпотентность, сбой без потери истории.

ВАЖНО: тесты разделяют одну БД (session-scoped), поэтому у каждого теста —
своя form_id: source_key = formId+responseId, общие ID дали бы ложные «дубли».
"""
import json
import time

from sqlalchemy import select

from app.db.models import Submission, SyncState
from app.sources.forms_poller.mock import MockFormsClient
from app.sources.forms_poller.poller import FormsPoller, response_to_raw, spec_from_form_entry


def _resp(form_id: str, rid: str, answers: list[tuple[str, str]], created="2026-05-01T10:00:00Z") -> dict:
    """Ответ в структуре Forms API (текстовые вопросы; ID вопроса — textQuestionId)."""
    return {
        "name": f"forms/{form_id}/responses/{rid}",
        "createTime": created,
        "answers": [
            {"question": {"textQuestion": {"textQuestionId": qid}, "title": qid},
             "selectedAnswers": [{"answer": value}]}
            for qid, value in answers
        ],
    }


def _entry(form_id: str) -> dict:
    return {
        "form_id": form_id,
        "role": "intern",
        "questionnaire": "intern_v1",
        "cycle_field": "Q_CYCLE",
        "about_intern_field": "Q_WHO",
        "question_map": {"Q_SKILL": "skill_growth", "Q_COMMENT": "comment_intern"},
    }


def _poller(client, form_id: str) -> FormsPoller:
    return FormsPoller(client=client, entries=[_entry(form_id)], interval_seconds=1)


def test_sync_stores_responses(catalog_db):
    fid = "F_SYNC"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4"), ("Q_COMMENT", "Хорошо")])
    r2 = _resp(fid, "R2", [("Q_CYCLE", "3"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "3")])
    poller = _poller(MockFormsClient({fid: [[r1, r2]]}), fid)
    results = poller.sync_once()

    assert results[f"form:{fid}"]["ok"] is True
    assert results[f"form:{fid}"]["created"] == 2

    # считаем только ответы этой формы (в общей БД сессии могут быть и чужие form-отправки)
    subs = list(catalog_db.scalars(select(Submission).where(Submission.source_key.like(f"{fid}:%"))))
    assert len(subs) == 2
    s1 = next(s for s in subs if s.source_key == f"{fid}:R1")
    assert s1.cycle == 2 and s1.role == "intern"
    assert s1.about_intern_id is not None
    answers = {a.question_key: a for a in s1.answers}
    assert answers["skill_growth"].score == 4.0
    assert answers["comment_intern"].text == "Хорошо"
    assert s1.submitted_at is not None

    state = catalog_db.scalar(select(SyncState).where(SyncState.connector == f"form:{fid}"))
    assert state.last_success_at is not None and state.last_error is None


def test_resync_no_duplicates(catalog_db):
    fid = "F_RESYNC"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4")])
    r2 = _resp(fid, "R2", [("Q_CYCLE", "3"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "3")])
    poller = _poller(MockFormsClient({fid: [[r1, r2]]}), fid)
    poller.sync_once()
    results = poller.sync_once()  # повторное чтение

    assert results[f"form:{fid}"]["created"] == 0
    assert results[f"form:{fid}"]["updated"] == 2
    count = len(list(catalog_db.scalars(select(Submission).where(Submission.source_key.like(f"{fid}:%")))))
    assert count == 2  # дублей нет


def test_sync_failure_keeps_history(catalog_db):
    fid = "F_FLAKY"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4")])
    r2 = _resp(fid, "R2", [("Q_CYCLE", "3"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "3")])

    class FlakyClient(MockFormsClient):
        def __init__(self):
            super().__init__({fid: [[r1, r2]]})
            self.calls = 0

        def iter_responses(self, form_id):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("network down")
            return super().iter_responses(form_id)

    poller = _poller(FlakyClient(), fid)
    first = poller.sync_once()
    assert first[f"form:{fid}"]["ok"] is True

    second = poller.sync_once()
    assert second[f"form:{fid}"]["ok"] is False
    assert "network down" in second[f"form:{fid}"]["error"]

    state = catalog_db.scalar(select(SyncState).where(SyncState.connector == f"form:{fid}"))
    assert state.last_error == "network down"
    assert state.last_success_at is not None  # время последней УСПЕШНОЙ синхронизации сохранено
    count = len(list(catalog_db.scalars(select(Submission).where(Submission.source_key.like(f"{fid}:%")))))
    assert count == 2  # история не стёрта


def test_pagination(catalog_db):
    fid = "F_PAGES"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4")])
    r2 = _resp(fid, "R2", [("Q_CYCLE", "3"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "3")])
    poller = _poller(MockFormsClient({fid: [[r1], [r2]]}), fid)  # две страницы
    results = poller.sync_once()
    assert results[f"form:{fid}"]["created"] == 2


def test_new_response_appears_on_next_sync(catalog_db, tmp_path):
    """Демо-флоу: новый ответ в источнике → подхвачен следующим проходом."""
    fid = "F_NEW"
    file = tmp_path / "responses.jsonl"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4")])
    file.write_text(json.dumps({"form_id": fid, "response": r1}, ensure_ascii=False) + "\n", encoding="utf-8")

    poller = _poller(MockFormsClient(path=file), fid)
    first = poller.sync_once()
    assert first[f"form:{fid}"]["created"] == 1

    r3 = _resp(fid, "R3", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "2")])
    with open(file, "a", encoding="utf-8") as f:
        f.write(json.dumps({"form_id": fid, "response": r3}, ensure_ascii=False) + "\n")
    second = poller.sync_once()
    assert second[f"form:{fid}"]["created"] == 1 and second[f"form:{fid}"]["updated"] == 1
    count = len(list(catalog_db.scalars(select(Submission).where(Submission.source_key.like(f"{fid}:%")))))
    assert count == 2


def test_spec_and_parse():
    entry = _entry("F_PARSE")
    spec = spec_from_form_entry(entry)
    assert spec.source == "form" and spec.role == "intern"
    assert spec.cycle_field == "cycle"
    assert spec.field_map == {"skill_growth": "skill_growth", "comment_intern": "comment_intern"}
    assert spec.about_intern_field == "about_intern"

    resp = _resp("F_PARSE", "RX", [("Q_CYCLE", "1"), ("Q_WHO", "Анна"), ("Q_SKILL", "5"), ("Q_COMMENT", "Отлично")])
    raw = response_to_raw(entry, resp)
    assert raw.source_key == "F_PARSE:RX"
    assert raw.payload["cycle"] == "1"
    assert raw.payload["about_intern"] == "Анна"
    assert raw.payload["skill_growth"] == "5"
    assert raw.payload["comment_intern"] == "Отлично"


def test_poller_background_thread(catalog_db):
    """Фоновый цикл: старт → синхронизация → остановка."""
    fid = "F_THREAD"
    r1 = _resp(fid, "R1", [("Q_CYCLE", "2"), ("Q_WHO", "Стажёр Формы"), ("Q_SKILL", "4")])
    poller = FormsPoller(MockFormsClient({fid: [[r1]]}), entries=[_entry(fid)], interval_seconds=1)
    poller.start()
    try:
        deadline = time.time() + 5
        state = None
        while time.time() < deadline:
            state = catalog_db.scalar(select(SyncState).where(SyncState.connector == f"form:{fid}"))
            if state is not None and state.last_success_at is not None:
                break
            time.sleep(0.05)
        assert state is not None and state.last_success_at is not None
    finally:
        poller.stop()
    count = len(list(catalog_db.scalars(select(Submission).where(Submission.source_key.like(f"{fid}:%")))))
    assert count == 1
