"""Tests of the /ask API contract for response_language (see also
test_rag_engine_i18n.py for the engine's internal logic)."""

from conftest import FakeRagEngine
from test_ask import _ask_result


class RecordingFakeRagEngine(FakeRagEngine):
    """Same behavior as FakeRagEngine, but remembers the received
    response_language value — to check that it does flow through
    schemas.AskRequest -> main.ask() -> engine.ask() without being lost."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.derniere_langue_recue: str | None = None

    def ask(self, question: str, top_k: int = 8, response_language: str = "fr") -> dict:
        self.derniere_langue_recue = response_language
        return super().ask(question, top_k, response_language)


def test_ask_default_response_language_is_french(make_client, auth_headers):
    engine = RecordingFakeRagEngine(ask_result=_ask_result("COMPLETE"))
    client = make_client(engine)

    resp = client.post("/ask", json={"question": "Bonjour ?"}, headers=auth_headers)

    assert resp.status_code == 200
    assert engine.derniere_langue_recue == "fr"


def test_ask_accepts_en_and_de(make_client, auth_headers):
    for langue in ("en", "de"):
        engine = RecordingFakeRagEngine(ask_result=_ask_result("COMPLETE"))
        client = make_client(engine)

        resp = client.post(
            "/ask", json={"question": "Bonjour ?", "response_language": langue}, headers=auth_headers
        )

        assert resp.status_code == 200
        assert engine.derniere_langue_recue == langue


def test_ask_rejects_invalid_response_language(make_client, auth_headers):
    client = make_client(FakeRagEngine(ask_result=_ask_result("COMPLETE")))

    resp = client.post(
        "/ask", json={"question": "Bonjour ?", "response_language": "es"}, headers=auth_headers
    )

    # Pydantic validation (Literal["fr","en","de"]): rejected before even
    # reaching the RAG engine.
    assert resp.status_code == 422
