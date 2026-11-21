import pytest
import yaml

from app.sources.forms_poller.client import FormsClient

INTERN_ID = "1IX04y4qW1OFC63i9z4I5BTAuerSygq2IPK1PqyyN7ik"
MENTOR_ID = "1gZ4-DBtonxKuW6i8Z9BKvesuGPEOSg9aoK9pLwOd2qs"


def _response(created, answers):
    return {
        "createTime": created,
        "answers": {
            qid: {"questionId": qid, "textAnswers": {"answers": [{"value": value}]}}
            for qid, value in answers.items()
        },
    }


@pytest.fixture
def responses(monkeypatch):
    intern = {"i-score": "4", "i-cycle": "2", "i-name": "TEST-01"}
    mentor = {"m-author": "MENTOR-01", "m-score": "3", "m-name": "TEST-01", "m-cycle": "2"}
    data = {
        INTERN_ID: [
            _response("2026-11-21T07:03:45.999Z", intern),
            _response("2026-11-21T07:03:46.123456Z", intern),
        ],
        MENTOR_ID: [
            _response("2026-11-21T07:03:00.900Z", {**mentor, "m-score": "5"}),
            _response("2026-11-21T07:03:00.900Z", mentor),
        ],
    }

    def offline_get(self, path, params):
        form_id = path.split("/")[3]
        if not params.get("pageToken"):
            return {"responses": data[form_id][:1], "nextPageToken": "second"}
        return {"responses": data[form_id][1:]}

    monkeypatch.setattr(FormsClient, "_get", offline_get)
    return data


def test_prints_config_from_both_control_responses(responses, capsys):
    from app.sources.forms_poller.prepare_pilot_config import main

    assert main() == 0
    assert yaml.safe_load(capsys.readouterr().out)["forms"] == [
        {
            "form_id": INTERN_ID, "role": "intern", "questionnaire": "intern_v1",
            "cycle_field": "i-cycle", "about_intern_field": "i-name",
            "submitted_at_field": "createTime", "question_map": {"i-score": "skill_growth"},
        },
        {
            "form_id": MENTOR_ID, "role": "mentor", "questionnaire": "mentor_v1",
            "cycle_field": "m-cycle", "about_intern_field": "m-name",
            "author_mentor_field": "m-author", "submitted_at_field": "createTime",
            "question_map": {"m-score": "skill_growth_mentor"},
        },
    ]


@pytest.mark.parametrize("match_count", [0, 2])
def test_prints_no_config_without_one_matching_response_per_form(responses, capsys, match_count):
    from app.sources.forms_poller.prepare_pilot_config import main

    mentor_matches = responses[MENTOR_ID][1:]
    responses[MENTOR_ID][1:] = mentor_matches * match_count

    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert f"mentor: найдено контрольных ответов: {match_count}" in output.err
