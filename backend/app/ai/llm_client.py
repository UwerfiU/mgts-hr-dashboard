"""Тонкий клиент для любого OpenAI-совместимого /chat/completions эндпоинта.

Подходит для: OpenAI, Azure (через прокси), Ollama (/v1/chat/completions),
LM Studio, локальных и корпоративных LLM-шлюзов.
"""
import json
import re

import httpx

from ..config import settings


def _parse_json(content: str) -> dict | None:
    """Достаём JSON из ответа модели (в т.ч. если обёрнут в ```json)."""
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\{.*\}", content or "", re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, system: str, user: str) -> dict | None:
        """Запрос к модели с ожиданием JSON-ответа. None при любой ошибке."""
        if not self.available:
            return None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        # Сначала пробуем строгий response_format; если провайдер его не
        # поддерживает (обычно 400) — повторяем без него.
        for use_response_format in (True, False):
            payload: dict = {"model": self.model, "messages": messages, "temperature": 0.2}
            if use_response_format:
                payload["response_format"] = {"type": "json_object"}
            try:
                r = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if r.status_code == 400 and use_response_format:
                    continue
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return _parse_json(content)
            except Exception:
                if use_response_format:
                    continue
                return None
        return None


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
