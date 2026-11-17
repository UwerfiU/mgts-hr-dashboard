"""Политики доступа и режимы данных (config/permissions.yaml).

Семантика флагов:
  * personal_slices_allowed — разрешены ли персональные срезы (?internId/?mentorId)
    в /metrics и /feedback. Требует подтверждённой связи «ответ → человек» (WP7).
  * numeric_history_allowed — доп. разрешение на ЧИСЛОВУЮ индивидуальную историю
    (персональные срезы /metrics). Проверяется вместе с personal_slices_allowed.
  * texts_allowed — показ текстовых комментариев в /feedback. Разрешается отдельно
    от числовой истории: даже при открытой истории тексты могут быть скрыты.

expected_per_cycle — план ответов на цикл (для coverage.expected); null — план
неизвестен, фронт не показывает процент охвата.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import settings


def _load() -> dict:
    path = Path(settings.permissions_path)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _cached(mtime_ns: int, size: int) -> dict:
    """Кэш на время жизни процесса; перезагружается при изменении файла."""
    return _load()


def permissions() -> dict:
    path = Path(settings.permissions_path)
    if not path.exists():
        return {}
    st = path.stat()
    return _cached(st.st_mtime_ns, st.st_size)


def personal_slices_allowed() -> bool:
    return bool(permissions().get("personal_slices_allowed", False))


def numeric_history_allowed() -> bool:
    return bool(permissions().get("numeric_history_allowed", False))


def texts_allowed() -> bool:
    """Показ текстов: в режиме demo (синтетические данные) — автоматически;
    в real — только явным флагом text_display_allowed."""
    if settings.data_mode == "demo":
        return True
    return bool(permissions().get("text_display_allowed", False))


def expected_per_cycle() -> dict[str, int | None] | None:
    """План ответов на цикл: {"intern": 5, "mentor": 5}; None — план неизвестен."""
    value = permissions().get("expected_per_cycle")
    if not isinstance(value, dict):
        return None
    out = {}
    for role in ("intern", "mentor"):
        v = value.get(role)
        out[role] = int(v) if isinstance(v, int) and v > 0 else None
    return out


def min_sample_for_insights() -> int:
    return int(permissions().get("min_sample_for_insights", 3))
