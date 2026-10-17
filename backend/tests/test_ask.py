from conftest import FakeRagEngine


def _ask_result(status: str, answer: str = "réponse", sources=None, claims=None) -> dict:
    return {
        "answer": answer,
        "status": status,
        "sources": sources or [],
        "validated_claims": claims or [],
        "timings": {
            "recherche_secondes": 0.01,
            "generation_secondes": 0.02,
            "total_secondes": 0.03,
        },
    }


def test_ask_requires_api_key(make_client):
    client = make_client(FakeRagEngine(ask_result=_ask_result("COMPLETE")))
    resp = client.post("/ask", json={"question": "test"})
    assert resp.status_code == 401


def test_ask_complete_returns_sources_and_claims(make_client, auth_headers):
    resultat = _ask_result(
        "COMPLETE",
        answer="Les mots de passe font au moins 14 caractères.",
        sources=[{"fichier": "politique_securite.txt", "page": 1, "extrait": "...", "score": 0.91}],
        claims=[
            {
                "affirmation": "Les mots de passe font au moins 14 caractères.",
                "fichier": "politique_securite.txt",
                "page": 1,
                "citation": "Les mots de passe doivent contenir au moins 14 caractères.",
                "citation_presente": True,
                "preuve_supported": True,
            }
        ],
    )
    client = make_client(FakeRagEngine(ask_result=resultat))

    resp = client.post(
        "/ask", json={"question": "Quelle est la longueur minimale d'un mot de passe ?"}, headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETE"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["fichier"] == "politique_securite.txt"
    assert len(body["validated_claims"]) == 1
    assert "request_id" in body and body["request_id"]


def test_ask_partial(make_client, auth_headers):
    resultat = _ask_result("PARTIAL", answer="- premier élément\n- deuxième élément")
    client = make_client(FakeRagEngine(ask_result=resultat))

    resp = client.post("/ask", json={"question": "Quels sont les chantiers ?"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "PARTIAL"


def test_ask_not_found(make_client, auth_headers):
    resultat = _ask_result("NOT_FOUND", answer="Information non trouvée dans les documents.")
    client = make_client(FakeRagEngine(ask_result=resultat))

    resp = client.post("/ask", json={"question": "Quel est le CA annuel d'AFTECH ?"}, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "NOT_FOUND"
    assert body["answer"] == "Information non trouvée dans les documents."
    assert body["validated_claims"] == []


def test_ask_rejects_question_over_2000_characters(make_client, auth_headers):
    client = make_client(FakeRagEngine(ask_result=_ask_result("COMPLETE")))
    resp = client.post("/ask", json={"question": "a" * 2001}, headers=auth_headers)
    assert resp.status_code == 422  # Pydantic validation (max_length=2000)


def test_ask_rejects_empty_question(make_client, auth_headers):
    client = make_client(FakeRagEngine(ask_result=_ask_result("COMPLETE")))
    resp = client.post("/ask", json={"question": ""}, headers=auth_headers)
    assert resp.status_code == 422
