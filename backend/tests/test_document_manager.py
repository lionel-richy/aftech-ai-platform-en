import numpy as np
import pytest
from pdf_helpers import pdf_valide

from app import index_builder
from app.document_manager import DocumentDejaIndexe, DocumentIntrouvable, DocumentManager
from app.document_pipeline import FichierInvalide

pytestmark = pytest.mark.asyncio


class FakeEmbedder:
    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.random.RandomState(0).rand(len(textes), 4).astype("float32")


class FakeEngine:
    """Simulates just enough of RagEngine for DocumentManager: a real
    embedder (pure numpy) and a reloadable chunks/index state."""

    def __init__(self, chunks_historiques_initiaux=None):
        self.embedder = FakeEmbedder()
        self.chunks = list(chunks_historiques_initiaux or [])
        self.index = None
        self.manifest = {}
        self.rechargements: list[str] = []

    def chunks_historiques(self, noms_affiches_geres):
        return [c for c in self.chunks if c["source"] not in noms_affiches_geres]

    def recharger_index(self, dossier_index):
        import json

        import faiss

        self.index = faiss.read_index(f"{dossier_index}/index.faiss")
        with open(f"{dossier_index}/chunks.json", encoding="utf-8") as f:
            self.chunks = json.load(f)
        with open(f"{dossier_index}/manifest.json", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.rechargements.append(dossier_index)

    def documents(self):
        return []  # no "historical" document in these tests


@pytest.fixture
def gestionnaire(tmp_path):
    return DocumentManager(str(tmp_path), FakeEngine())


class TestDepotEtTraitement:
    async def test_depot_puis_traitement_aboutit_a_ready(self, gestionnaire):
        enregistrement = await gestionnaire.deposer(pdf_valide(), "rapport.pdf")
        assert enregistrement.statut == "UPLOADED"

        await gestionnaire.traiter(enregistrement.id)

        doc = gestionnaire.obtenir_statut(enregistrement.id)
        assert doc["statut"] == "READY"
        assert doc["nb_pages"] == 1
        assert doc["nb_passages"] >= 1

    async def test_deux_depots_differents_restent_independants(self, gestionnaire):
        a = await gestionnaire.deposer(pdf_valide(texte="Contenu A."), "a.pdf")
        b = await gestionnaire.deposer(pdf_valide(texte="Contenu B."), "b.pdf")
        await gestionnaire.traiter(a.id)
        await gestionnaire.traiter(b.id)

        documents = gestionnaire.lister_tout()
        noms = {d["nom_fichier"] for d in documents}
        assert noms == {"a.pdf", "b.pdf"}
        assert all(d["statut"] == "READY" for d in documents)

    async def test_doublon_rejete_des_le_depot(self, gestionnaire):
        contenu = pdf_valide()
        await gestionnaire.deposer(contenu, "premier.pdf")

        with pytest.raises(DocumentDejaIndexe):
            await gestionnaire.deposer(contenu, "copie_renommee.pdf")

    async def test_echec_extraction_marque_failed_avec_message_non_sensible(self, gestionnaire, monkeypatch):
        enregistrement = await gestionnaire.deposer(pdf_valide(), "rapport.pdf")

        def extraction_cassee(*_args, **_kwargs):
            # SYNC (not async): index_builder calls it via
            # asyncio.to_thread(extraire_chunks_pdf, ...), which requires a
            # synchronous callable — a coroutine would never actually run.
            raise RuntimeError("/var/secret/internal/path blew up")

        monkeypatch.setattr(index_builder, "extraire_chunks_pdf", extraction_cassee)

        with pytest.raises(RuntimeError):
            await gestionnaire.traiter(enregistrement.id)

        doc = gestionnaire.obtenir_statut(enregistrement.id)
        assert doc["statut"] == "FAILED"
        assert doc["message_erreur"] is not None

    async def test_fichier_invalide_rejete_avant_tout_enregistrement(self, gestionnaire):
        with pytest.raises(FichierInvalide):
            await gestionnaire.deposer(b"pas un pdf", "x.pdf")
        assert gestionnaire.lister_tout() == []


class TestSuppression:
    async def test_suppression_retire_le_document_et_reconstruit_lindex(self, gestionnaire):
        a = await gestionnaire.deposer(pdf_valide(texte="Contenu A."), "a.pdf")
        b = await gestionnaire.deposer(pdf_valide(texte="Contenu B."), "b.pdf")
        await gestionnaire.traiter(a.id)
        await gestionnaire.traiter(b.id)

        await gestionnaire.supprimer(a.id)

        assert gestionnaire.obtenir_statut(a.id) is None
        restants = {d["nom_fichier"] for d in gestionnaire.lister_tout()}
        assert restants == {"b.pdf"}
        # The engine did reload an index that no longer contains "a.pdf".
        sources_actives = {c["source"] for c in gestionnaire.engine.chunks}
        assert "a.pdf" not in sources_actives
        assert "b.pdf" in sources_actives

    async def test_suppression_document_inconnu_leve_document_introuvable(self, gestionnaire):
        with pytest.raises(DocumentIntrouvable):
            await gestionnaire.supprimer("id-qui-nexiste-pas")

    async def test_apres_suppression_le_fichier_pdf_est_bien_retire_du_disque(self, gestionnaire):
        import os

        a = await gestionnaire.deposer(pdf_valide(), "a.pdf")
        await gestionnaire.traiter(a.id)
        chemin = gestionnaire.registry.chemin_pdf(a.id)
        assert os.path.isfile(chemin)

        await gestionnaire.supprimer(a.id)

        assert not os.path.isfile(chemin)


class TestFusionHistoriqueEtGere:
    async def test_documents_historiques_non_supprimables_restent_listes(self, tmp_path):
        engine = FakeEngine()
        engine.documents = lambda: [
            {
                "nom_fichier": "ancien.pdf",
                "pages": 10,
                "passages": 20,
                "hash_sha256": "deadbeef",
                "modele_embeddings": "BAAI/bge-m3",
                "date_index": "2026-01-01T00:00:00+00:00",
            }
        ]
        gestionnaire = DocumentManager(str(tmp_path), engine)

        documents = gestionnaire.lister_tout()

        assert len(documents) == 1
        assert documents[0]["nom_fichier"] == "ancien.pdf"
        assert documents[0]["supprimable"] is False
