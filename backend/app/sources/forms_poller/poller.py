"""Синхронизация Google Forms: разбор ответов → RawRecord → нормализация → БД.

Цикл: при запуске + по интервалу (фоновый поток). Полная перечитка обеих форм
(объём кейса мал), upsert по formId+responseId — повторное чтение не дублирует.
Сбой одной формы не влияет на другую и не стирает историю (см. sync_state).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading

from ...db.database import SessionLocal
from ...normalization.core import normalize_and_store
from ...normalization.report import NormalizationReport
from ...normalization.spec import SourceSpec
from ...sources.base import RawRecord
from .client import iter_answers, parse_response_time
from .sync_state import set_sync_state

logger = logging.getLogger("mgts.forms")


def _fallback_response_id(resp: dict) -> str:
    """Стабильный id, если Forms API не вернул responseId: хеш содержимого ответа."""
    basis = {
        "createTime": resp.get("createTime"),
        "lastSubmittedTime": resp.get("lastSubmittedTime"),
        "answers": resp.get("answers"),
    }
    blob = json.dumps(basis, sort_keys=True, ensure_ascii=False, default=str)
    return "sha1-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def response_to_raw(entry: dict, resp: dict) -> RawRecord:
    """Ответ Forms API → RawRecord с payload в ВНУТРЕННИХ ключах вопросов.

    Синтетические поля payload (не из каталога):
      * "cycle"         — значение вопроса-цикла (entry["cycle_field"]);
      * "about_intern"  — значение вопроса «о ком» (entry["about_intern_field"]);
      * "author_mentor" — псевдоним автора (entry["author_mentor_field"]).
    """
    form_id = entry["form_id"]
    resp_id = str(resp.get("responseId") or "").strip()
    if not resp_id:
        # Запасной вариант: name вида forms/{formId}/responses/{id}, иначе хеш.
        name = str(resp.get("name") or "")
        resp_id = name.rsplit("/", 1)[-1] if "/" in name else ""
    if not resp_id:
        resp_id = _fallback_response_id(resp)

    qmap: dict[str, str] = entry.get("question_map") or {}
    payload: dict = {}
    for qid, value in iter_answers(resp):
        if qid == entry.get("cycle_field"):
            payload["cycle"] = value
        elif qid == entry.get("about_intern_field"):
            payload["about_intern"] = value
        elif qid == entry.get("author_mentor_field"):
            payload["author_mentor"] = value
        elif qid in qmap:
            payload[qmap[qid]] = value

    submitted_field = entry.get("submitted_at_field") or "createTime"
    submitted_at = parse_response_time(resp.get(submitted_field)) or parse_response_time(resp.get("createTime"))

    return RawRecord(
        source="form",
        source_key=f"{form_id}:{resp_id}",  # устойчивый ключ — основа идемпотентности
        payload=payload,
        submitted_at=submitted_at,
    )


def spec_from_form_entry(entry: dict) -> SourceSpec:
    """SourceSpec для формы: payload уже во внутренних ключах → identity-маппинг."""
    qmap: dict[str, str] = entry.get("question_map") or {}
    return SourceSpec(
        source="form",
        role=entry["role"],
        questionnaire=entry["questionnaire"],
        cycle_field="cycle",
        field_map={k: k for k in qmap.values()},
        about_intern_field="about_intern" if entry.get("about_intern_field") else None,
        author_mentor_field="author_mentor" if entry.get("author_mentor_field") else None,
    )


class FormsPoller:
    """Фоновая синхронизация: старт + повтор по интервалу."""

    def __init__(self, client, entries: list[dict], interval_seconds: int, db_factory=SessionLocal):
        self.client = client
        self.entries = entries
        self.interval_seconds = max(1, int(interval_seconds))
        self.db_factory = db_factory
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- синхронизация -------------------------------------------------------

    def sync_once(self) -> dict[str, dict]:
        """Один проход по всем формам. Возвращает результаты по коннекторам."""
        results: dict[str, dict] = {}
        db = self.db_factory()
        try:
            for entry in self.entries:
                form_id = entry.get("form_id")
                connector = f"form:{form_id}"
                if not form_id:
                    msg = "form_id не задан в конфиге sources_forms.yaml"
                    set_sync_state(db, connector, error=msg)
                    results[connector] = {"ok": False, "error": msg}
                    logger.error("sync %s: %s", connector, msg)
                    continue
                try:
                    records = [response_to_raw(entry, r) for r in self.client.iter_responses(form_id)]
                    report: NormalizationReport = normalize_and_store(db, records, spec_from_form_entry(entry))
                    from ...db.models import utcnow

                    set_sync_state(db, connector, success_at=utcnow())
                    results[connector] = {"accepted": report.accepted, "created": report.created,
                                          "updated": report.updated, "skipped": len(report.skipped), "ok": True}
                    logger.info("sync %s: принято=%d новых=%d обновлено=%d", connector,
                                report.accepted, report.created, report.updated)
                except Exception as e:  # noqa: BLE001 — сбой одной формы не роняет остальные
                    db.rollback()
                    set_sync_state(db, connector, error=str(e))
                    results[connector] = {"ok": False, "error": str(e)}
                    logger.error("sync %s: ошибка: %s", connector, e)
        finally:
            db.close()
        return results

    # --- фоновый цикл ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mgts-forms-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync_once()
            except Exception as e:  # noqa: BLE001 — защита цикла от непредвиденного
                logger.exception("poller: ошибка прохода: %s", e)
            self._stop.wait(self.interval_seconds)
