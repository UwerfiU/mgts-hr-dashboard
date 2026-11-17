"""Анализ текстовых комментариев: LLM (основной путь) + лексиконный fallback.

Результат — словарь с полями:
    sentiment_score  float  -1..1
    sentiment_label  str    positive | neutral | negative
    risk_level       str    low | medium | high
    issues           list[str]
    summary          str | None
    provider         str    llm | lexicon | none
"""
import re

from .llm_client import get_llm_client

SYSTEM_PROMPT = """Ты — аналитик HR-данных, помогающий отслеживать прохождение
шестимесячной программы стажировок. Тебе дают текстовый комментарий стажёра или
наставника из ежемесячного опроса. Оцени эмоциональный тон и выяви признаки
проблем (выгорание, демотивация, конфликт с наставником, непонятные задачи,
низкая вовлечённость).

Верни строго JSON в формате:
{
  "sentiment_score": <число от -1 до 1>,
  "sentiment_label": "positive" | "neutral" | "negative",
  "risk_level": "low" | "medium" | "high",
  "issues": ["краткая проблема 1", "..."],
  "summary": "1-2 предложения: суть комментария и оценка риска"
}
Если проблем нет — issues = []."""

USER_TEMPLATE = 'Комментарий (месяц программы: {month}): "{text}"'


def _normalize(data: dict, provider: str) -> dict:
    try:
        score = float(data.get("sentiment_score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(-1.0, min(1.0, score))
    label = data.get("sentiment_label")
    if label not in ("positive", "neutral", "negative"):
        label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
    risk = data.get("risk_level")
    if risk not in ("low", "medium", "high"):
        risk = "low"
    issues = [str(x) for x in (data.get("issues") or []) if str(x).strip()]
    summary = str(data.get("summary") or "").strip() or None
    return {
        "sentiment_score": round(score, 2),
        "sentiment_label": label,
        "risk_level": risk,
        "issues": issues,
        "summary": summary,
        "provider": provider,
    }


# --- Лексиконный fallback (работает офлайн, без LLM) -------------------------

POS_WORDS = [
    "хорошо", "отлично", "спасибо", "благодар", "интересно", "понятно",
    "поддерживает", "помогает", "удовлетвор", "развиваюсь", "уверен",
    "дружелюбн", "комфортно", "ценю", "полезно", "наставник супер",
]

NEG_WORDS = [
    "плохо", "проблем", "сложно", "тяжело", "не понимаю", "непонятн",
    "не помогает", "выгораю", "устал", "демотивац", "конфликт",
    "низк", "задерживают", "хаос", "стресс", "беспокоит", "разочарован",
]

STRONG_NEG_PATTERNS = [
    r"уволюсь", r"покину", r"не вижу смысла", r"хочу уйти", r"больше не буду",
]


def _lexicon(text: str) -> dict:
    lower = text.lower()
    pos_hits = sum(1 for w in POS_WORDS if w in lower)
    neg_hits = sum(1 for w in NEG_WORDS if w in lower)
    strong = any(re.search(p, lower) for p in STRONG_NEG_PATTERNS)

    total = pos_hits + neg_hits
    score = (pos_hits - neg_hits) / total if total else 0.0
    label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"

    if strong or score <= -0.75:
        risk = "high"
    elif score < -0.3 or (label == "negative" and neg_hits >= 2):
        risk = "medium"
    else:
        risk = "low"

    issues = [w for w in NEG_WORDS if w in lower]
    summary = f"Лексиконный анализ: {label} (поз. слов: {pos_hits}, негативных: {neg_hits})"
    return {
        "sentiment_score": round(score, 2),
        "sentiment_label": label,
        "risk_level": risk,
        "issues": issues,
        "summary": summary,
        "provider": "lexicon",
    }


def analyze_comment(text: str | None, month: int = 0) -> dict:
    """Главная точка входа: проанализировать комментарий."""
    if not text or not text.strip():
        return {
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "risk_level": "low",
            "issues": [],
            "summary": None,
            "provider": "none",
        }

    client = get_llm_client()
    if client.available:
        data = client.complete_json(SYSTEM_PROMPT, USER_TEMPLATE.format(month=month, text=text))
        if data:
            return _normalize(data, "llm")
    return _lexicon(text)
