from conftest import FakeRagEngine


def test_health_ready_does_not_require_api_key(make_client):
    client = make_client(FakeRagEngine(ready=True))
    resp = client.get("/health")  # no Authorization header
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ready"] is True
    assert body["documents_count"] == 3
    assert body["chunks_count"] == 353


def test_health_exposes_real_gpu_and_vram_when_ready(make_client):
    client = make_client(FakeRagEngine(ready=True))
    resp = client.get("/health")
    body = resp.json()
    assert body["gpu"] == "Tesla L4"
    assert body["vram_totale_octets"] > 0
    assert body["vram_utilisee_octets"] > 0
    assert body["vram_utilisee_octets"] < body["vram_totale_octets"]


def test_health_degraded_when_engine_not_ready(make_client):
    client = make_client(FakeRagEngine(ready=False))
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["ready"] is False


def test_health_vram_is_none_not_zero_when_unavailable(make_client):
    """Never a 0 that would look like a real GPU measurement."""
    client = make_client(FakeRagEngine(ready=False))
    resp = client.get("/health")
    body = resp.json()
    assert body["vram_totale_octets"] is None
    assert body["vram_utilisee_octets"] is None
