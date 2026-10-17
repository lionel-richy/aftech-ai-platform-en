import numpy as np
import pytest
from fastapi.testclient import TestClient
from pdf_helpers import pdf_valide

from app.document_manager import DocumentManager
from app.main import app, get_document_manager


class FakeEmbedder:
    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.random.RandomState(0).rand(len(textes), 4).astype("float32")


class FakeEngineAvecEmbedder:
    def __init__(self):
        self.embedder = FakeEmbedder()
        self.chunks = []
        self.index = None
        self.manifest = {}

    def chunks_historiques(self, noms):
        return [c for c in self.chunks if c["source"] not in noms]

    def recharger_index(self, dossier_index):
        import json

        import faiss

        self.index = faiss.read_index(f"{dossier_index}/index.faiss")
        with open(f"{dossier_index}/chunks.json", encoding="utf-8") as f:
            self.chunks = json.load(f)
        with open(f"{dossier_index}/manifest.json", encoding="utf-8") as f:
            self.manifest = json.load(f)

    def documents(self):
        return []


@pytest.fixture
def client_documents(tmp_path):
    gestionnaire = DocumentManager(str(tmp_path), FakeEngineAvecEmbedder())
    app.dependency_overrides[get_document_manager] = lambda: gestionnaire
    client = TestClient(app)
    yield client, gestionnaire
    app.dependency_overrides.clear()
    client.close()


class TestUpload:
    def test_upload_sans_cle_api_rejete(self, client_documents):
        client, _ = client_documents
        resp = client.post("/documents", files={"fichier": ("x.pdf", pdf_valide(), "application/pdf")})
        assert resp.status_code == 401

    def test_upload_pdf_valide_accepte_et_traite_en_tache_de_fond(self, client_documents, auth_headers):
        client, gestionnaire = client_documents
        resp = client.post(
            "/documents",
            files={"fichier": ("rapport.pdf", pdf_valide(), "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        corps = resp.json()
        assert corps["statut"] == "UPLOADED"
        assert corps["nom_original"] == "rapport.pdf"

        # TestClient runs BackgroundTasks synchronously before returning the
        # response to the test client (Starlette's standard behavior in
        # tests): the document must therefore already be processed.
        doc = gestionnaire.obtenir_statut(corps["id"])
        assert doc["statut"] == "READY"

    def test_upload_mauvais_type_rejete_422(self, client_documents, auth_headers):
        client, _ = client_documents
        resp = client.post(
            "/documents",
            files={"fichier": ("notes.txt", b"du texte brut", "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_upload_pdf_vide_rejete_422(self, client_documents, auth_headers):
        client, _ = client_documents
        resp = client.post(
            "/documents", files={"fichier": ("vide.pdf", b"", "application/pdf")}, headers=auth_headers
        )
        assert resp.status_code == 422

    def test_upload_doublon_rejete_409(self, client_documents, auth_headers):
        client, _ = client_documents
        contenu = pdf_valide()
        client.post("/documents", files={"fichier": ("a.pdf", contenu, "application/pdf")}, headers=auth_headers)

        resp = client.post(
            "/documents", files={"fichier": ("copie.pdf", contenu, "application/pdf")}, headers=auth_headers
        )
        assert resp.status_code == 409

    def test_liste_documents_inclut_le_document_traite(self, client_documents, auth_headers):
        client, _ = client_documents
        client.post(
            "/documents", files={"fichier": ("rapport.pdf", pdf_valide(), "application/pdf")}, headers=auth_headers
        )

        resp = client.get("/documents", headers=auth_headers)
        assert resp.status_code == 200
        documents = resp.json()
        assert len(documents) == 1
        assert documents[0]["nom_fichier"] == "rapport.pdf"
        assert documents[0]["statut"] == "READY"
        assert documents[0]["supprimable"] is True


class TestStatut:
    def test_statut_document_inconnu_404(self, client_documents, auth_headers):
        client, _ = client_documents
        resp = client.get("/documents/id-inconnu/status", headers=auth_headers)
        assert resp.status_code == 404

    def test_statut_sans_cle_api_rejete(self, client_documents):
        client, _ = client_documents
        resp = client.get("/documents/x/status")
        assert resp.status_code == 401


class TestSuppression:
    def test_suppression_sans_cle_api_rejetee(self, client_documents):
        client, _ = client_documents
        resp = client.delete("/documents/x")
        assert resp.status_code == 401

    def test_suppression_document_inconnu_404(self, client_documents, auth_headers):
        client, _ = client_documents
        resp = client.delete("/documents/id-inconnu", headers=auth_headers)
        assert resp.status_code == 404

    def test_suppression_document_existant_fonctionne(self, client_documents, auth_headers):
        client, gestionnaire = client_documents
        resp_upload = client.post(
            "/documents", files={"fichier": ("rapport.pdf", pdf_valide(), "application/pdf")}, headers=auth_headers
        )
        id_document = resp_upload.json()["id"]

        resp = client.delete(f"/documents/{id_document}", headers=auth_headers)

        assert resp.status_code == 204
        assert gestionnaire.obtenir_statut(id_document) is None
