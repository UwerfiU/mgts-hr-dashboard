"""WP3: импорт Excel — dry-run, идемпотентность, замена партии, отчёт, CLI."""
import json
from pathlib import Path

import pytest
import yaml
from openpyxl import Workbook
from sqlalchemy import select

from app.db.models import Submission
from app.sources.excel_importer.cli import import_file, main as cli_main
from app.sources.excel_importer.reader import file_fingerprint, read_records


def make_xlsx(path: Path, header: list[str], rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


HEADER = ["trainee_name", "month", "score_skill", "score_tasks", "score_mentor",
          "score_motivation", "score_overall", "comment_text"]

# ВАЖНО: openpyxl создаёт побайтово одинаковые файлы для одинакового содержимого,
# а file_row_hash строится от содержимого. Поэтому у каждого теста — СВОИ данные:
# иначе source_key совпадёт с другим тестом (общая БД в рамках сессии).
def _rows(prefix: str) -> list[list]:
    return [
        [f"{prefix} Анна", 1, 4, 4, 5, 4, 4, "Хороший месяц"],
        [f"{prefix} Дмитрий", 1, 3, 3, 4, 3, 3, None],
        [f"{prefix} Сергей", 2, 5, 4, 4, 5, 4, "Отлично"],
    ]


def _entry(record_key=None) -> dict:
    return {
        "path": "",
        "role": "intern",
        "questionnaire": "intern_v1",
        "cycle_field": "month",
        "about_intern_field": "trainee_name",
        "field_map": {
            "score_skill": "skill_growth",
            "score_tasks": "task_clarity",
            "score_mentor": "mentor_support",
            "score_motivation": "motivation",
            "score_overall": "satisfaction",
            "comment_text": "comment_intern",
        },
        "record_key": record_key or {"type": "file_row_hash", "columns": ["trainee_name", "month"]},
    }


def test_import_creates_submissions(catalog_db, tmp_path):
    xlsx = make_xlsx(tmp_path / "i1.xlsx", HEADER, _rows("Импорт"))
    r = import_file(catalog_db, xlsx, _entry())
    assert (r.accepted, r.created) == (3, 0 + 3) and not r.skipped

    subs = list(catalog_db.scalars(select(Submission).where(Submission.source == "excel")))
    assert len(subs) == 3
    batch_id = file_fingerprint(xlsx)
    assert all(s.file_batch_id == batch_id for s in subs)

    smirnova = next(s for s in subs if s.about_intern_id is not None and s.cycle == 1
                    and any(a.question_key == "skill_growth" and a.score == 4.0 for a in s.answers))
    assert smirnova is not None


def test_reimport_same_file_no_duplicates(catalog_db, tmp_path):
    xlsx = make_xlsx(tmp_path / "i2.xlsx", HEADER, _rows("Реримпорт"))
    r1 = import_file(catalog_db, xlsx, _entry())
    r2 = import_file(catalog_db, xlsx, _entry())
    assert (r1.created, r1.updated) == (3, 0)
    assert (r2.created, r2.updated) == (0, 3)  # повтор того же файла не увеличивает число ответов
    batch_id = file_fingerprint(xlsx)
    count = len(list(catalog_db.scalars(
        select(Submission).where(Submission.file_batch_id == batch_id))))
    assert count == 3


def test_dry_run_writes_nothing(catalog_db, tmp_path):
    xlsx = make_xlsx(tmp_path / "i3.xlsx", HEADER, _rows("Драйран"))
    before = len(list(catalog_db.scalars(select(Submission))))
    r = import_file(catalog_db, xlsx, _entry(), dry_run=True)
    assert r.accepted == 3  # валидация прошла
    after = len(list(catalog_db.scalars(select(Submission))))
    assert after == before  # запись в БД не произошло


def test_bad_rows_in_report(catalog_db, tmp_path):
    rows = [
        ["Нормальная Анна", 1, 4, 4, 4, 4, 4, None],
        ["Битаяшка Борис", 1, 9, 4, 4, 4, 4, None],   # оценка вне шкалы
        ["Циклик Вера", 7, 4, 4, 4, 4, 4, None],      # цикл вне 1–6
    ]
    xlsx = make_xlsx(tmp_path / "i4.xlsx", HEADER, rows)
    r = import_file(catalog_db, xlsx, _entry())
    assert (r.accepted, len(r.skipped)) == (1, 2)
    reasons = " | ".join(p.reason for p in r.skipped)
    assert "шкалы" in reasons and "цикл" in reasons
    assert r.ok


def test_replace_batch(catalog_db, tmp_path):
    v1 = make_xlsx(tmp_path / "i5_v1.xlsx", HEADER, _rows("Замена"))
    batch_v1 = file_fingerprint(v1)
    import_file(catalog_db, v1, _entry())

    rows_v2 = [list(r) for r in _rows("Замена")]
    rows_v2[0][2] = 2  # исправленная версия: другая оценка → другой отпечаток файла
    v2 = make_xlsx(tmp_path / "i5_v2.xlsx", HEADER, rows_v2)
    batch_v2 = file_fingerprint(v2)
    assert batch_v1 != batch_v2

    r = import_file(catalog_db, v2, _entry(), replace_batch_id=batch_v1)
    assert r.created == 3
    old = list(catalog_db.scalars(select(Submission).where(Submission.file_batch_id == batch_v1)))
    new = list(catalog_db.scalars(select(Submission).where(Submission.file_batch_id == batch_v2)))
    assert len(old) == 0 and len(new) == 3  # старая партия заменена


def test_stable_id_key(catalog_db, tmp_path):
    """stable_id: ключ строки не зависит от файла — правка значения обновляет запись на месте."""
    entry = _entry(record_key={"type": "stable_id", "column": "code"})
    header = ["code", "trainee_name", "month", "score_skill"]
    fmap_entry = dict(entry)
    fmap_entry["field_map"] = {"score_skill": "skill_growth"}

    f1 = make_xlsx(tmp_path / "i6_v1.xlsx", header, [["C1", "Анна", 1, 4], ["C2", "Борис", 1, 3]])
    import_file(catalog_db, f1, fmap_entry)

    f2 = make_xlsx(tmp_path / "i6_v2.xlsx", header, [["C2", "Борис", 2, 2], ["C1", "Анна", 2, 5]])
    r = import_file(catalog_db, f2, fmap_entry)  # без replace-batch: ключи те же
    assert (r.created, r.updated) == (0, 2)

    subs = list(catalog_db.scalars(select(Submission).where(Submission.source_key.like("stable:%"))))
    assert len(subs) == 2  # дублей нет


def test_missing_config_column_is_config_error(catalog_db, tmp_path):
    """Опечатка в field_map — ошибка конфига, а не тихий NULL."""
    xlsx = make_xlsx(tmp_path / "e1.xlsx", HEADER, _rows("Колонки"))
    entry = _entry()
    entry["field_map"]["score_typo"] = "task_clarity"
    with pytest.raises(ValueError, match="нет столбцов"):
        import_file(catalog_db, xlsx, entry)


def test_duplicate_headers_rejected(tmp_path):
    xlsx = make_xlsx(
        tmp_path / "e2.xlsx",
        ["trainee_name", "month", "score_skill", "score_skill"],
        [["Анна", 1, 4, 2]],
    )
    with pytest.raises(ValueError, match="дублирующиеся заголовки"):
        read_records(xlsx, None, {"type": "file_row_hash", "columns": ["trainee_name"]})


def test_empty_record_key_columns_rejected(catalog_db, tmp_path):
    """Без колонок ключа весь файл схлопнулся бы в одну запись — это ошибка."""
    xlsx = make_xlsx(tmp_path / "e3.xlsx", HEADER, _rows("Ключ"))
    with pytest.raises(ValueError, match="columns"):
        import_file(catalog_db, xlsx, _entry({"type": "file_row_hash", "columns": []}))


def test_duplicate_source_key_in_batch_skipped(catalog_db, tmp_path):
    rows = [
        ["Дубль Анна", 1, 4, 4, 4, 4, 4, None],
        ["Дубль Анна", 1, 5, 5, 5, 5, 5, None],  # тот же (trainee_name, month)
    ]
    xlsx = make_xlsx(tmp_path / "e4.xlsx", HEADER, rows)
    r = import_file(catalog_db, xlsx, _entry())
    assert r.accepted == 1 and r.created == 1
    assert any("дубликат" in p.reason for p in r.skipped)
    keys = list(catalog_db.scalars(
        select(Submission.source_key).where(Submission.file_batch_id == file_fingerprint(xlsx))))
    assert len(keys) == 1


def test_invalid_file_keeps_old_batch(catalog_db, tmp_path):
    """--replace-batch не должен удалять старую партию, если новый файл битый."""
    v1 = make_xlsx(tmp_path / "e5_v1.xlsx", HEADER, _rows("Сохранить"))
    batch_v1 = file_fingerprint(v1)
    import_file(catalog_db, v1, _entry())

    bad = make_xlsx(tmp_path / "e5_bad.xlsx", ["trainee_name", "month"], [["Анна", 1]])
    with pytest.raises(ValueError):
        import_file(catalog_db, bad, _entry(), replace_batch_id=batch_v1)

    still = list(catalog_db.scalars(
        select(Submission).where(Submission.file_batch_id == batch_v1)))
    assert len(still) == 3


def test_cli_exit_code_when_all_rows_skipped(catalog_db, tmp_path):
    xlsx = make_xlsx(
        tmp_path / "e6.xlsx", HEADER,
        [["Плохой Анна", 9, 4, 4, 4, 4, 4, None]],  # цикл вне диапазона
    )
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(yaml.safe_dump({"files": [{**_entry(), "path": str(xlsx)}]}, allow_unicode=True),
                   encoding="utf-8")
    assert cli_main(["--config", str(cfg)]) == 1


def test_module_entrypoint_available():
    import subprocess
    import sys

    backend = Path(__file__).parent.parent
    r = subprocess.run(
        [sys.executable, "-m", "app.sources.excel_importer", "--help"],
        cwd=backend, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "--replace-batch" in r.stdout


def test_mentor_file_sets_author(catalog_db, tmp_path):
    """Excel наставников: author_mentor_field заполняет автора → работает фильтр mentorId."""
    header = ["mentor_name", "intern_name", "month", "score_skill"]
    xlsx = make_xlsx(tmp_path / "e7.xlsx", header,
                     [["Наставник Э", "Стажёр Э", 1, 4]])
    entry = {
        "path": "", "role": "mentor", "questionnaire": "mentor_v1",
        "cycle_field": "month", "about_intern_field": "intern_name",
        "author_mentor_field": "mentor_name",
        "field_map": {"score_skill": "skill_growth_mentor"},
        "record_key": {"type": "file_row_hash", "columns": ["mentor_name", "intern_name", "month"]},
    }
    r = import_file(catalog_db, xlsx, entry)
    assert r.accepted == 1
    sub = catalog_db.scalar(select(Submission).where(
        Submission.file_batch_id == file_fingerprint(xlsx)))
    assert sub.author_mentor_id is not None


def test_cli_end_to_end(catalog_db, tmp_path, capsys):
    xlsx = make_xlsx(tmp_path / "i7.xlsx", HEADER, _rows("Кли"))
    cfg = tmp_path / "sources_excel.yaml"
    cfg.write_text(yaml.safe_dump({"files": [{**_entry(), "path": str(xlsx)}]}, allow_unicode=True), encoding="utf-8")

    # dry-run через CLI
    before = len(list(catalog_db.scalars(select(Submission))))
    rc = cli_main(["--config", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "[dry-run]" in out and "Принято: 3" in out
    assert len(list(catalog_db.scalars(select(Submission)))) == before

    # полноценный импорт + JSON-отчёт
    report_json = tmp_path / "report.json"
    rc = cli_main(["--config", str(cfg), "--report-json", str(report_json)])
    out = capsys.readouterr().out
    assert rc == 0 and "Принято: 3" in out
    data = json.loads(report_json.read_text(encoding="utf-8"))
    entry_report = next(iter(data.values()))
    assert entry_report["accepted"] == 3 and entry_report["ok"] is True
    assert len(list(catalog_db.scalars(select(Submission)))) == before + 3
