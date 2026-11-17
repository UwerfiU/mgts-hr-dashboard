"""Чтение Excel-файлов в RawRecord (openpyxl) — часть коннектора WP3."""
from __future__ import annotations

import hashlib
from pathlib import Path

from openpyxl import load_workbook

from ..base import RawRecord


def file_fingerprint(path: str | Path) -> str:
    """Стабильный отпечаток файла (sha256, первые 16 hex) — id Excel-партии."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _make_source_key(record_key_cfg: dict, payload: dict, file_hash: str) -> str:
    """Ключ записи в источнике по правилу из конфига.

    * stable_id      — явный столбец с устойчивым ID строки;
    * file_row_hash  — отпечаток (файл + ключевые столбцы): повтор того же файла
                       даёт тот же ключ (идемпотентность), а исправленная версия
                       файла — другие ключи (загружается как новая партия).
    """
    rtype = (record_key_cfg or {}).get("type", "file_row_hash")
    if rtype == "stable_id":
        col = record_key_cfg.get("column")
        value = payload.get(col)
        if value is None or str(value).strip() == "":
            raise ValueError(f"stable_id: столбец '{col}' пуст — нужен устойчивый ID строки")
        return f"stable:{str(value).strip()}"
    if rtype == "file_row_hash":
        cols = record_key_cfg.get("columns") or []
        parts = "|".join(str(payload.get(c, "")).strip() for c in cols)
        row_hash = hashlib.sha1(parts.encode("utf-8")).hexdigest()[:12]
        return f"{file_hash}:{row_hash}"
    raise ValueError(f"Неизвестный тип record_key: {rtype!r}")


def read_records(file_path: str | Path, sheet: str | None, record_key_cfg: dict) -> list[RawRecord]:
    """Строки листа → RawRecord. payload = {заголовок столбца: значение ячейки}."""
    path = Path(file_path)
    file_hash = file_fingerprint(path)
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[sheet] if sheet else wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not rows:
        return []
    header = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]

    records: list[RawRecord] = []
    for row in rows[1:]:
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
            continue  # пустая строка
        payload = {header[i]: row[i] for i in range(min(len(header), len(row)))}
        records.append(
            RawRecord(
                source="excel",
                source_key=_make_source_key(record_key_cfg, payload, file_hash),
                payload=payload,
            )
        )
    return records
