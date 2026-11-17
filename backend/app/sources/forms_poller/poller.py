"""Синхронизация Google Forms: разбор ответов → RawRecord → нормализация → БД.

Цикл: при запуске + по интервалу (фоновый поток). Полная перечитка обеих форм
(объём кейса мал), upsert по formId+responseId — повторное чтение не дублирует.
Сбой одной формы не влияет на другую и не стирает историю (см. sync_state).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from ...db.database import SessionLocal
from ...normalization.core import normalize_and_store
from ...normalization.report import NormalizationReport
from ...normalization.spec import SourceSpec
from ...sources.base import RawRecord
from .sync_state import set_sync_state

logger = logging.getLogger("mgts.forms")


def _question_id(question: dict) -> str | None:
    """Стабильный ID вопроса из ответа Forms API (camelCase-поля)."""
    for kind in ("textQuestion", "multipleChoiceQuestion", "gridQuestion", "imageMultipleChoiceQuestion"):
        block = question.get(kind)
        if isinstance(block, dict):
            qid = block.get(f"{kind}Id")
            if qid:
                return qid
    return question.get("title") or None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def response_to_raw(entry: dict, resp: dict) -> RawRecord:
    """Ответ Forms API → RawRecord с payload в ВНУТРЕННИХ ключах вопросов.

    Синтетические поля payload (не из каталога):
      * "cycle"         — значение вопроса-цикла (entry["cycle_field"]);
      * "about_intern"  — значение вопроса «о ком» (entry["about_intern_field"]).
    """
    form_id = entry["form_id"]
    resp_id = str(resp.get("name", "")).rsplit("/", 1)[-1] or "unknown"
    qmap: dict[str, str] = entry.get("question_map") or {}

    payload: dict = {}
    for ans in resp.get("answers", []):
        question = ans.get("question") or {}
        qid = _question_id(question)
        if not qid:
            continue
        values = [sa.get("answer", "") for sa in ans.get("selectedAnswers", [])]
        value = "; ".join(v for v in values if v is not None and str(v).strip() != "")
        if qid == entry.get("cycle_field"):
            payload["cycle"] = value
        elif qid == entry.get("about_intern_field"):
            payload["about_intern"] = value
        elif qid in qmap:
            payload[qmap[qid]] = value

    return RawRecord(
        source="form",
        source_key=f"{form_id}:{resp_id}",  # устойчивый ключ — основа идемпотентности
        payload=payload,
        submitted_at=_parse_time(resp.get("createTime")),
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
                connector = f"form:{entry['form_id']}"
                try:
                    records = [response_to_raw(entry, r) for r in self.client.iter_responses(entry["form_id"])]
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
