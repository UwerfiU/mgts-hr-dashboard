"""Дымовой тест каркаса (WP0). Полноценные тесты — в WP5 (контракт /api/v1)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
