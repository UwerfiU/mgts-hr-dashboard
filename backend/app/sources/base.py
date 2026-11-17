"""Базовый контракт адаптеров источников (WP2).

Адаптер источника (Excel-ридер в WP3, Forms-клиент в WP4) читает «сырые»
записи и отдаёт их как RawRecord; дальше общая нормализация (app.normalization)
превращает их в канонические записи и сохраняет в БД. Форматы источников
разные — тип записи после нормализации один.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawRecord:
    """Сырая запись из источника, до нормализации."""

    source: str  # "excel" | "form"
    source_key: str  # стабильный ключ в источнике (formId+responseId / file_row_hash / stable_id)
    payload: dict  # поля как есть из источника
    submitted_at: datetime | None = None
    file_batch_id: str | None = None  # для Excel-партий (явная замена партии, WP3)
