"""CLI импорта исторических Excel-файлов (критерий B3, WP3).

Использование (из backend/):
    python -m app.sources.excel_importer [--config config/sources_excel.yaml]
                                         [--file data/intern_history.xlsx]...
                                         [--dry-run] [--replace-batch <batch_id>]
                                         [--report-json report.json]

Поведение:
  * формат каждого файла задаётся в конфиге (роль, анкета, лист, маппинг столбцов,
    правило цикла и ключа записи) — см. config/sources_excel.yaml;
  * повторный импорт того же файла не увеличивает число ответов (upsert по source_key);
  * исправленная версия файла без стабильных ID строки загружается как явная замена
    предыдущей партии: --replace-batch <id> удаляет записи старой партии только ПОСЛЕ
    успешной валидации нового файла (битый файл не уничтожает старые данные);
  * batch id файла = его отпечаток (виден в отчёте и в БД в Submission.file_batch_id);
  * --dry-run — полный прогон чтения и валидации БЕЗ записи в БД.

Код выхода: 0 — без ошибок, 1 — были ошибки обработки/конфигурации или файл
целиком отклонён валидацией (принято 0 записей при непустом отчёте).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from ...catalog.loader import load_catalog
from ...config import settings
from ...db.database import SessionLocal, init_db
from ...db.models import Answer, Submission
from ...normalization.core import normalize_batch, store_normalized
from ...normalization.report import NormalizationReport
from ...normalization.spec import SourceSpec
from .reader import file_fingerprint, read_records

DEFAULT_CONFIG = Path(settings.catalog_path).parent / "sources_excel.yaml"


def _resolve_path(path: str | Path, config_path: Path) -> Path:
    """Пути в конфиге трактуются относительно backend/ (родителя каталога config/)."""
    p = Path(path)
    if p.is_absolute():
        return p
    return config_path.resolve().parent.parent / p


def _required_columns(entry: dict) -> list[str]:
    """Колонки, без которых импорт по этой секции конфига не имеет смысла."""
    required: set[str] = set(entry.get("field_map") or {})
    for name in ("cycle_field", "about_intern_field", "author_mentor_field"):
        value = entry.get(name)
        if value:
            required.add(str(value))
    record_key = entry.get("record_key") or {}
    if record_key.get("type", "file_row_hash") == "stable_id":
        if record_key.get("column"):
            required.add(str(record_key["column"]))
    else:
        required.update(str(c) for c in (record_key.get("columns") or []))
    return sorted(required)


def spec_from_file_entry(entry: dict) -> SourceSpec:
    """SourceSpec из секции файла в sources_excel.yaml."""
    return SourceSpec(
        source="excel",
        role=entry["role"],
        questionnaire=entry["questionnaire"],
        cycle_field=entry["cycle_field"],
        field_map=dict(entry.get("field_map") or {}),
        about_intern_field=entry.get("about_intern_field"),
        author_mentor_field=entry.get("author_mentor_field"),
        submitted_at_field=entry.get("submitted_at_field"),
    )


def _report_ok(report: NormalizationReport) -> bool:
    """Успех файла: нет ошибок обработки и хотя бы часть строк принята.

    Файл, где все строки отклонены валидацией (например, неверная анкета в
    конфиге), — не успех, даже если `errors` пуст.
    """
    return report.ok and not (report.accepted == 0 and (report.skipped or report.errors))


def replace_batch(db, batch_id: str) -> int:
    """Явная замена партии: удалить старые записи с этим file_batch_id. Возвращает число удалённых."""
    sub_ids = select(Submission.id).where(
        Submission.source == "excel", Submission.file_batch_id == batch_id
    )
    db.execute(sql_delete(Answer).where(Answer.submission_id.in_(sub_ids)))
    result = db.execute(sql_delete(Submission).where(
        Submission.source == "excel", Submission.file_batch_id == batch_id
    ))
    db.commit()
    return result.rowcount or 0


def import_file(db, path: Path, entry: dict, dry_run: bool = False, replace_batch_id: str | None = None) -> NormalizationReport:
    """Импорт одного файла по его секции конфига.

    Порядок: чтение (с проверкой обязательных колонок) → нормализация → замена
    партии (только если есть что записывать) → сохранение. Так битый/пустой файл
    не удаляет предыдущую партию.
    """
    records = read_records(
        path,
        entry.get("sheet"),
        entry.get("record_key") or {},
        required_columns=_required_columns(entry),
    )
    batch_id = file_fingerprint(path)
    for r in records:
        r.file_batch_id = batch_id

    spec = spec_from_file_entry(entry)
    ok_records, report = normalize_batch(db, records, spec)

    if dry_run:
        report.accepted = len(ok_records)  # сколько было бы принято
        return report

    if replace_batch_id and ok_records:
        removed = replace_batch(db, replace_batch_id)
        if removed:
            print(f"  замена партии {replace_batch_id}: удалено записей: {removed}")

    return store_normalized(db, ok_records, report)


def _report_dict(report: NormalizationReport) -> dict:
    d = asdict(report)
    d["ok"] = report.ok
    return d


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Импорт исторических Excel-файлов в БД")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="путь к sources_excel.yaml")
    parser.add_argument("--file", action="append", default=None,
                        help="импортировать только указанный файл (можно несколько); по умолчанию — все из конфига")
    parser.add_argument("--dry-run", action="store_true", help="проверка без записи в БД")
    parser.add_argument("--replace-batch", default=None,
                        help="batch id старой партии для явной замены (исправленная версия файла)")
    parser.add_argument("--report-json", default=None, help="сохранить отчёт в JSON")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Конфиг не найден: {config_path}", file=sys.stderr)
        return 1
    files_cfg = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}).get("files") or []

    entries = files_cfg
    if args.file:
        wanted = {_resolve_path(f, config_path).resolve() for f in args.file}
        entries = [
            e for e in files_cfg
            if _resolve_path(e["path"], config_path).resolve() in wanted
        ]
        missing = wanted - {_resolve_path(e["path"], config_path).resolve() for e in entries}
        for m in missing:
            print(f"Файл не описан в конфиге: {m}", file=sys.stderr)
        if not entries:
            return 1

    init_db()
    db = SessionLocal()
    try:
        load_catalog(db)  # каталог должен быть актуален для валидации
        all_ok = True
        reports: dict[str, dict] = {}
        for entry in entries:
            path = _resolve_path(entry["path"], config_path)
            if not path.exists():
                print(f"Файл не найден: {path}", file=sys.stderr)
                all_ok = False
                continue
            mode = " [dry-run]" if args.dry_run else ""
            print(f"Импорт: {path}{mode}")
            try:
                report = import_file(
                    db, path, entry, dry_run=args.dry_run, replace_batch_id=args.replace_batch
                )
            except Exception as e:  # noqa: BLE001 — ошибка одного файла не должна ронять остальные
                db.rollback()
                print(f"  ошибка конфигурации/чтения файла: {e}", file=sys.stderr)
                reports[str(path)] = {"error": str(e)}
                all_ok = False
                continue
            print(report.summary_text())
            reports[str(path)] = _report_dict(report)
            all_ok = all_ok and _report_ok(report)

        if args.report_json:
            out = Path(args.report_json)
            out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Отчёт сохранён: {out}")
        return 0 if all_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
