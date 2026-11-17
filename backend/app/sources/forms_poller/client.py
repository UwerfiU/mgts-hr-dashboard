"""Клиент Google Forms API: чтение ответов формы (критерий B4, WP4).

Используется только чтение: GET /v1/forms/{formId}/responses с пагинацией.
Публичный адрес не нужен — Backend делает исходящие запросы.

OAuth (desktop flow, одноразовая настройка):
    python -m app.sources.forms_poller.setup_oauth
— откроется браузер (или напечатается URL), после подтверждения токен
сохранится в backend/secrets/forms_token.json (вне репозитория, .gitignore).

Зависимости google-auth/google-auth-oauthlib импортируются лениво: в режиме
demo сервис работает без них.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

BASE_URL = "https://forms.googleapis.com"
SCOPES = ["https://www.googleapis.com/auth/forms.responses.readonly"]


class FormsClientError(RuntimeError):
    pass


class FormsClient:
    def __init__(self, client_secrets_path: str, token_path: str, scopes: list[str] | None = None, timeout: float = 30.0):
        self.client_secrets_path = Path(client_secrets_path)
        self.token_path = Path(token_path)
        self.scopes = scopes or SCOPES
        self.timeout = timeout

    def _access_token(self) -> str:
        from google.auth.transport.requests import Request  # ленивый импорт
        from google.oauth2.credentials import Credentials

        if not self.token_path.exists():
            raise FormsClientError(
                f"Токен не найден: {self.token_path}. Выполните настройку: "
                "python -m app.sources.forms_poller.setup_oauth"
            )
        info = json.loads(self.token_path.read_text(encoding="utf-8"))
        creds = Credentials.from_authorized_user_info(info, self.scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")  # сохраняем обновлённый токен
            self.token_path.chmod(0o600)
        if not creds.valid:
            raise FormsClientError("OAuth-токен недействителен; повторите setup_oauth")
        return creds.token

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = httpx.get(
            BASE_URL + path,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            params=params or {},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise FormsClientError(f"Forms API {r.status_code}: {r.text[:300]}")
        return r.json()

    def iter_responses(self, form_id: str):
        """Все ответы формы (по страницам)."""
        page_token = None
        while True:
            params = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            data = self._get(f"/v1/forms/{form_id}/responses", params)
            for resp in data.get("responses", []):
                yield resp
            page_token = data.get("nextPageToken")
            if not page_token:
                return
