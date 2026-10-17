from conftest import FakeRagEngine


def _ask_result(answer: str = "ok", status: str = "COMPLETE") -> dict:
    return {
        "answer": answer,
        "status": status,
        "sources": [],
        "validated_claims": [],
        "timings": {"recherche_secondes": 0.0, "generation_secondes": 0.0, "total_secondes": 0.0},
    }


def test_chat_completions_requires_api_key(make_client):
    client = make_client(FakeRagEngine(ask_result=_ask_result()))
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "aftech-qwen3-4b", "messages": [{"role": "user", "content": "salut"}]},
    )
    assert resp.status_code == 401


def test_chat_completions_uses_last_user_message_and_matches_openai_shape(make_client, auth_headers):
    client = make_client(FakeRagEngine(ask_result=_ask_result(answer="Bonjour, comment puis-je aider ?")))
    payload = {
        "model": "aftech-qwen3-4b",
        "messages": [
            {"role": "system", "content": "contexte système"},
            {"role": "user", "content": "première question"},
            {"role": "assistant", "content": "première réponse"},
            {"role": "user", "content": "deuxième question, la seule qui doit être utilisée"},
        ],
        "temperature": 0.7,
    }

    resp = client.post("/v1/chat/completions", json=payload, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "aftech-qwen3-4b"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "Bonjour, comment puis-je aider ?"
    assert body["choices"][0]["finish_reason"] == "stop"
    # Not instrumented yet: always 0, never a made-up number.
    assert body["usage"]["total_tokens"] == 0


def test_chat_completions_requires_a_user_message(make_client, auth_headers):
    client = make_client(FakeRagEngine(ask_result=_ask_result()))
    payload = {"model": "aftech-qwen3-4b", "messages": [{"role": "system", "content": "contexte seulement"}]}

    resp = client.post("/v1/chat/completions", json=payload, headers=auth_headers)

    assert resp.status_code == 400
