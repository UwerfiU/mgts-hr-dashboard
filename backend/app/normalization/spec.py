"""Спецификация источника для нормализации (WP2).

SourceSpec описывает, КАК читать один источник: роль, анкета, откуда цикл,
кто автор и маппинг «сырое поле → внутренний ключ вопроса». Конкретные
коннекторы (WP3/WP4) строят SourceSpec из своих YAML-конфигов; нормализация
от формата источника не зависит.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceSpec:
    source: str  # "excel" | "form"
    role: str  # intern | mentor
    questionnaire: str  # qid анкеты из каталога
    cycle_field: str  # сырое поле с циклом (1–6)
    field_map: dict[str, str] = field(default_factory=dict)  # сырое поле → ключ вопроса
    about_intern_field: str | None = None  # сырое поле «о ком» (псевдоним стажёра); None — без связи
    author_mentor_field: str | None = None  # сырое поле с псевдонимом наставника (автора, для role=mentor)
    submitted_at_field: str | None = None  # сырое поле с датой (опционально)
