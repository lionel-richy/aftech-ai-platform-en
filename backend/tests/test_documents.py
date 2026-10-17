from conftest import FakeRagEngine


def test_documents_requires_api_key(make_client):
    client = make_client(FakeRagEngine())
    resp = client.get("/documents")
    assert resp.status_code == 401


def test_documents_rejects_wrong_key(make_client):
    client = make_client(FakeRagEngine())
    resp = client.get("/documents", headers={"Authorization": "Bearer mauvaise-cle"})
    assert resp.status_code == 401


def test_documents_with_valid_key_returns_real_manifest_shape(make_client, auth_headers):
    client = make_client(FakeRagEngine())
    resp = client.get("/documents", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    document = body[0]
    assert document["nom_fichier"].endswith(".pdf")
    assert document["pages"] > 0
    assert document["passages"] > 0
    assert document["hash_sha256"]
