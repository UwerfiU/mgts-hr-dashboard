"""Вывод sources_forms.yaml для двух контрольных анкет после настройки OAuth.

Из backend/: python -m app.sources.forms_poller.prepare_pilot_config
Команда печатает YAML после проверки обеих анкет. Для сохранения вывода
используйте отдельный файл, чтобы ошибка чтения не затронула текущий конфиг.
"""

import sys
from datetime import datetime

import httpx
import yaml

from ...config import settings
from .client import SCOPES, FormsClient, FormsClientError, iter_answers, parse_response_time

PILOT_FORMS = (
    ("intern", "1IX04y4qW1OFC63i9z4I5BTAuerSygq2IPK1PqyyN7ik",
     "2026-11-21T10:03:46+03:00", "skill_growth",
     {"cycle_field": "2", "about_intern_field": "TEST-01", "score": "4"}),
    ("mentor", "1gZ4-DBtonxKuW6i8Z9BKvesuGPEOSg9aoK9pLwOd2qs",
     "2026-11-21T10:03:00+03:00", "skill_growth_mentor",
     {"cycle_field": "2", "about_intern_field": "TEST-01",
      "author_mentor_field": "MENTOR-01", "score": "3"}),
)


class PilotMatchError(ValueError):
    pass


def _form_entry(
    client: FormsClient, role: str, form_id: str, timestamp: str,
    score_key: str, control_values: dict[str, str],
) -> dict:
    expected_time = datetime.fromisoformat(timestamp)
    expected_values = sorted(control_values.values())
    matches = []
    for response in client.iter_responses(form_id):
        created = parse_response_time(response.get("createTime"))
        if created is None or created.replace(microsecond=0) != expected_time:
            continue
        answers = list(iter_answers(response))
        if (sorted(value for _, value in answers) == expected_values
                and len({qid for qid, _ in answers}) == len(answers)):
            matches.append({value: qid for qid, value in answers})

    if len(matches) != 1:
        raise PilotMatchError(f"{role}: найдено контрольных ответов: {len(matches)}, ожидался один")

    mapping = {field: matches[0][value] for field, value in control_values.items()}
    score_question_id = mapping.pop("score")
    return {
        "form_id": form_id,
        "role": role,
        "questionnaire": f"{role}_v1",
        **mapping,
        "submitted_at_field": "createTime",
        "question_map": {score_question_id: score_key},
    }


def main() -> int:
    client = FormsClient(
        client_secrets_path=settings.google_client_secrets_file,
        token_path=settings.google_token_cache,
    )
    try:
        forms = [_form_entry(client, *form) for form in PILOT_FORMS]
    except (PilotMatchError, FormsClientError, httpx.HTTPError) as error:
        print(error, file=sys.stderr)
        return 1

    config = {
        "sync": {"interval_seconds": 120, "strategy": "full_reread"},
        "forms": forms,
        "google": {"client_secrets_env": "MGTS_GOOGLE_CLIENT_SECRETS_FILE", "scopes": SCOPES},
    }
    sys.stdout.write(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
