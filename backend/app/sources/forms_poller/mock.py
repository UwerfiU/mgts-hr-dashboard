"""Mock-коннектор форм: синтетические ответы для офлайн-демо и тестов.

Имитирует интерфейс FormsClient (iter_responses) без сети: источники ответов —
встроенные списки или JSONL-файл (строка = один ответ). Для демо на защите:
добавить строку в файл → следующий проход poller'а подхватит «новый ответ».
"""
from __future__ import annotations

import json
from pathlib import Path


class MockFormsClient:
    def __init__(self, pages_by_form: dict[str, list[list[dict]]] | None = None, path: str | Path | None = None):
        """pages_by_form: {form_id: [страница1(ответы), страница2...]} — для проверки пагинации.
        path: JSONL-файл; строки вида {"form_id":..., "response": {...}} (можно дополнять на лету)."""
        self.pages_by_form = pages_by_form or {}
        self.path = Path(path) if path else None

    def _from_file(self, form_id: str):
        if not self.path or not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if item.get("form_id") == form_id:
                yield item["response"]

    def iter_responses(self, form_id: str):
        for page in self.pages_by_form.get(form_id, []):
            yield from page
        yield from self._from_file(form_id)
