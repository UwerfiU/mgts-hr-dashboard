"""Общие фикстуры: изолированная тестовая БД (env выставляется ДО импорта app)."""
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="mgts_test_")
os.environ["MGTS_DB_URL"] = f"sqlite:///{(Path(_tmp) / 'test.db').as_posix()}"
os.environ["MGTS_DATA_MODE"] = "demo"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # запускает lifespan → init_db()
        yield c
