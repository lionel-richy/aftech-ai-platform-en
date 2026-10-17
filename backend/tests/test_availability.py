from conftest import FakeRagEngine


def test_availability_returns_ok_without_api_key(make_client):
    # ready=False: proves that /availability still answers "ok" — it does
    # NOT depend on the AI engine's state (Qwen/BGE-M3), unlike /health.
    # No Authorization header either: no sensitive information is
    # returned.
    client = make_client(FakeRagEngine(ready=False))
    resp = client.get("/availability")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_availability_does_not_call_engine_ask_or_health(make_client, monkeypatch):
    """/availability must NEVER read the engine's state — it shouldn't even
    call engine.health()."""
    engine = FakeRagEngine(ready=True)
    appels = []
    health_original = engine.health
    engine.health = lambda: (appels.append("health") or health_original())  # noqa: E731

    client = make_client(engine)
    client.get("/availability")

    assert appels == []
