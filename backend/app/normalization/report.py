"""Отчёт о нормализации/импорте (WP2): принято, пропущено с причинами, ошибки."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RowProblem:
    source_key: str
    reason: str


@dataclass
class NormalizationReport:
    accepted: int = 0
    created: int = 0  # новых отправок
    updated: int = 0  # обновлённых (повтор того же source_key)
    skipped: list[RowProblem] = field(default_factory=list)  # отклонено валидацией
    errors: list[RowProblem] = field(default_factory=list)  # непредвиденные сбои обработки

    def skip(self, source_key: str, reason: str) -> None:
        self.skipped.append(RowProblem(source_key, reason))

    def error(self, source_key: str, reason: str) -> None:
        self.errors.append(RowProblem(source_key, reason))

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary_text(self) -> str:
        """Человекочитаемая сводка для stdout (WP3)."""
        lines = [
            f"Принято: {self.accepted} (новых: {self.created}, обновлено: {self.updated})",
            f"Пропущено: {len(self.skipped)}",
            f"Ошибок: {len(self.errors)}",
        ]
        for p in self.skipped:
            lines.append(f"  - пропущено [{p.source_key}]: {p.reason}")
        for p in self.errors:
            lines.append(f"  - ошибка [{p.source_key}]: {p.reason}")
        return "\n".join(lines)
