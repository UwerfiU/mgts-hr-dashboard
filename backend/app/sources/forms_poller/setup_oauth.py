"""Одноразовая настройка OAuth для Google Forms (desktop flow).

Использование (из backend/):
    python -m app.sources.forms_poller.setup_oauth [--secrets <путь к client_secrets.json>]

Откроется браузер (или напечатается URL) → подтвердить доступ → токен сохранится
в backend/secrets/forms_token.json. Файлы секретов вне репозитория (.gitignore).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...config import settings
from .client import SCOPES


def main() -> int:
    parser = argparse.ArgumentParser(description="Настройка OAuth для Google Forms")
    parser.add_argument("--secrets", default=settings.google_client_secrets_file,
                        help="путь к client_secrets.json (или MGTS_GOOGLE_CLIENT_SECRETS_FILE)")
    args = parser.parse_args()

    if not args.secrets or not Path(args.secrets).exists():
        print(
            "Файл client secrets не найден. Создайте проект в Google Cloud Console:\n"
            "  1. Enable API: Google Forms API\n"
            "  2. Credentials → Create OAuth client ID → Desktop app\n"
            "  3. Сохраните JSON и укажите путь: --secrets <путь> или MGTS_GOOGLE_CLIENT_SECRETS_FILE",
            file=sys.stderr,
        )
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow  # ленивый импорт

    flow = InstalledAppFlow.from_client_secrets_file(args.secrets, SCOPES)
    creds = flow.run_console()  # интерактивно: браузер + код подтверждения
    token_path = Path(settings.google_token_cache)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Токен сохранён: {token_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
