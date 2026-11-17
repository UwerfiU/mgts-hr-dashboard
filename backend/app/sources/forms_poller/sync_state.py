"""Статус коннекторов синхронизации (таблица SyncState) — для /api/v1/meta и диагностики.

Семантика:
  * last_success_at — время последней УСПЕШНОЙ синхронизации коннектора;
  * last_error      — текст последней ошибки (сбрасывается при успешной синхронизации);
  * сбой НЕ стирает историю данных — только фиксирует ошибку и время.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import SyncState, utcnow


def set_sync_state(db: Session, connector: str, success_at: datetime | None = None, error: str | None = None) -> None:
    row = db.scalar(select(SyncState).where(SyncState.connector == connector))
    if row is None:
        row = SyncState(connector=connector)
        db.add(row)
    if success_at is not None:
        row.last_success_at = success_at
        row.last_error = None  # успешная синхронизация сбрасывает ошибку
    elif error is not None:
        row.last_error = error  # last_success_at остаётся прежним
    row.updated_at = utcnow()
    db.commit()


def get_sync_states(db: Session) -> list[SyncState]:
    return list(db.scalars(select(SyncState).order_by(SyncState.connector)))
