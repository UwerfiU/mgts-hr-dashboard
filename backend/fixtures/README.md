"""Фикстуры — JSON-реализация контракта /api/v1 для фронтенда (контракт BACKEND.md).

Фронт работает с одним клиентом и двумя реализациями: фикстуры (локально) и HTTP.
Фикстуры повторяют контракт, включая фильтры и состояния недоступности
(«пусто» vs «запрещено»). Заполняются в WP5; здесь — только описание набора.

Планируемый набор (минимум):
  meta/ok.json                 — полный /meta на демо-наборе
  metrics/coverage_partial.json— неполный охват (submitted < expected)
  metrics/expected_null.json   — план ответов неизвестен (expected: null)
  metrics/month_gap.json       — пропущенный месяц в series (value: null, не 0)
  metrics/comparison_available.json
  metrics/comparison_unavailable.json — пары не настроены / связи нет
  metrics/personal_forbidden.json     — персональный срез запрещён (код ≠ пустота)
  feedback/texts_allowed.json
  feedback/texts_forbidden.json       — тексты скрыты, числовая аналитика доступна
"""
