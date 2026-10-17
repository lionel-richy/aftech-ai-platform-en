import asyncio
import json
import os
import time

import numpy as np
import pytest
from pdf_helpers import pdf_valide

from app.document_pipeline import DocumentRegistry, EnregistrementDocument
from app.index_builder import (
    IndexInvalide,
    ReconstructionDejaEnCours,
    VerrouReconstruction,
    chemin_index_courant,
    reconstruire_index,
    rollback_vers_version_precedente,
)

pytestmark = pytest.mark.asyncio


class FakeEmbedder:
    """Pure numpy, like in test_rag_engine_validation.py: we're not testing
    embedding quality, only the rebuild mechanics."""

    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.random.RandomState(0).rand(len(textes), 4).astype("float32")


def _enregistrer_pdf(tmp_path, registry: DocumentRegistry, nom: str, statut="READY") -> dict:
    os.makedirs(os.path.join(str(tmp_path), "documents"), exist_ok=True)
    contenu = pdf_valide()
    nom_stocke = f"{nom}.pdf"
    with open(os.path.join(str(tmp_path), "documents", nom_stocke), "wb") as f:
        f.write(contenu)
    enregistrement = EnregistrementDocument(
        id=nom,
        nom_original=f"{nom}.pdf",
        nom_stocke=nom_stocke,
        taille_octets=len(contenu),
        hash_sha256=f"hash-{nom}",
        nb_pages=1,
        statut=statut,
    )
    registry.ajouter(enregistrement)
    return registry.obtenir(nom)


class TestReconstructionAtomique:
    async def test_reconstruction_reussie_cree_index_current(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "doc1")

        manifest = await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

        dossier_courant = chemin_index_courant(str(tmp_path))
        assert os.path.isfile(os.path.join(dossier_courant, "index.faiss"))
        assert os.path.isfile(os.path.join(dossier_courant, "chunks.json"))
        assert manifest["pdf"] == ["doc1.pdf"]

    async def test_chunks_historiques_sont_conserves_sans_reextraction(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "nouveau")
        historiques = [{"source": "ancien.pdf", "page": 1, "texte": "Texte historique jamais ré-extrait.", "position": 0}]

        await reconstruire_index(historiques, [doc], registry, FakeEmbedder(), str(tmp_path))

        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            chunks = json.load(f)
        sources = {c["source"] for c in chunks}
        assert "ancien.pdf" in sources
        assert "nouveau.pdf" in sources

    async def test_version_precedente_devient_rollback(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))

        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        await reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        dossier_precedent = os.path.join(str(tmp_path), "index", "previous")
        assert os.path.isdir(dossier_precedent)
        with open(os.path.join(dossier_precedent, "manifest.json"), encoding="utf-8") as f:
            manifest_precedent = json.load(f)
        assert manifest_precedent["pdf"] == ["v1.pdf"]  # the old version, not the new one

    async def test_rollback_restaure_la_version_precedente(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc1 = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc1], registry, FakeEmbedder(), str(tmp_path))
        doc2 = _enregistrer_pdf(tmp_path, registry, "v2")
        await reconstruire_index([], [doc1, doc2], registry, FakeEmbedder(), str(tmp_path))

        reussi = rollback_vers_version_precedente(str(tmp_path))

        assert reussi is True
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

    async def test_rollback_sans_version_precedente_renvoie_false(self, tmp_path):
        assert rollback_vers_version_precedente(str(tmp_path)) is False

    async def test_aucun_document_actif_produit_un_index_vide_mais_valide(self, tmp_path):
        # Library fully emptied (last document deleted): a LEGITIMATE
        # state, not an error — see EmptyState on the frontend side.
        registry = DocumentRegistry(str(tmp_path))
        manifest = await reconstruire_index([], [], registry, FakeEmbedder(), str(tmp_path))

        assert manifest["pdf"] == []
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "chunks.json"), encoding="utf-8") as f:
            assert json.load(f) == []

    async def test_echec_de_construction_ne_touche_pas_current_et_ne_laisse_pas_de_dossier_building(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc_valide = _enregistrer_pdf(tmp_path, registry, "v1")
        await reconstruire_index([], [doc_valide], registry, FakeEmbedder(), str(tmp_path))

        # A document whose PDF, referenced by the registry, no longer
        # exists on disk (e.g. volume corruption): extraire_chunks_pdf
        # really fails, with no need to mock anything.
        doc_cassee = EnregistrementDocument(
            id="casse", nom_original="casse.pdf", nom_stocke="fichier-absent.pdf",
            taille_octets=1, hash_sha256="x", statut="READY",
        )
        registry.ajouter(doc_cassee)

        with pytest.raises(FileNotFoundError):
            await reconstruire_index([], [doc_valide, registry.obtenir("casse")], registry, FakeEmbedder(), str(tmp_path))

        # "current" (the version that worked) was not replaced.
        with open(os.path.join(chemin_index_courant(str(tmp_path)), "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["pdf"] == ["v1.pdf"]

        dossier_index = os.path.join(str(tmp_path), "index")
        restants = [n for n in os.listdir(dossier_index) if n.startswith("building-")]
        assert restants == []


class EmbedderLent(FakeEmbedder):
    """Simulates BGE-M3's real CPU cost (an encode() call that takes
    time), to prove that ANOTHER request can run interleaved WHILE a
    rebuild is in progress — this is exactly the real bug hit in
    production (the whole container froze, Modal eventually killed it
    mid-processing, leaving a document stuck forever)."""

    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        time.sleep(0.02)  # a bit of real CPU work per batch, not instant
        return super().encode(textes, convert_to_numpy, normalize_embeddings)


class TestReconstructionNeBloquePasLaBoucleDEvenements:
    async def test_une_autre_tache_async_sintercale_pendant_la_reconstruction(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        # Enough passages for the rebuild to take several batches
        # (TAILLE_LOT_EMBEDDING=64), so several real tens of milliseconds.
        historiques = [
            {"source": "gros.pdf", "page": 1, "texte": f"Passage historique numéro {i}.", "position": i}
            for i in range(300)
        ]

        evenements: list[str] = []

        async def autre_requete_pendant_ce_temps():
            for _ in range(20):
                await asyncio.sleep(0.005)
                evenements.append("autre_requete")

        resultat_reconstruction, _ = await asyncio.gather(
            reconstruire_index(historiques, [], registry, EmbedderLent(), str(tmp_path)),
            autre_requete_pendant_ce_temps(),
        )

        # The proof: "autre_requete" got to run SEVERAL times WHILE the
        # rebuild was in progress, not just before or after — impossible
        # if the rebuild had monopolized the event loop.
        assert len(evenements) >= 10
        assert resultat_reconstruction["pdf"] == ["gros.pdf"]


class TestVerrouReconstruction:
    async def test_deux_verrous_simultanes_le_second_echoue(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            with pytest.raises(ReconstructionDejaEnCours):
                with VerrouReconstruction(str(tmp_path)):
                    pass

    async def test_verrou_libere_apres_le_bloc(self, tmp_path):
        with VerrouReconstruction(str(tmp_path)):
            pass
        with VerrouReconstruction(str(tmp_path)):  # raises nothing: the first was properly released
            pass

    async def test_reconstruction_concurrente_leve_reconstruction_deja_en_cours(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "v1")
        dossier_index = os.path.join(str(tmp_path), "index")
        os.makedirs(dossier_index, exist_ok=True)

        with VerrouReconstruction(dossier_index):
            with pytest.raises(ReconstructionDejaEnCours):
                await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

    async def test_verrou_perime_est_automatiquement_repris(self, tmp_path, monkeypatch):
        """Real bug: a container killed mid-processing leaves the lock
        orphaned forever. A lock that's too old must be reclaimed
        automatically rather than blocking indefinitely."""
        import app.index_builder as index_builder_module
        from datetime import datetime, timedelta, timezone

        registry = DocumentRegistry(str(tmp_path))
        doc = _enregistrer_pdf(tmp_path, registry, "v1")
        dossier_index = os.path.join(str(tmp_path), "index")
        os.makedirs(dossier_index, exist_ok=True)

        chemin_verrou = os.path.join(dossier_index, ".reindex.lock")
        horodatage_perime = datetime.now(timezone.utc) - timedelta(seconds=index_builder_module.AGE_MAX_VERROU_SECONDES + 60)
        with open(chemin_verrou, "w", encoding="utf-8") as f:
            f.write(horodatage_perime.isoformat())

        manifest = await reconstruire_index([], [doc], registry, FakeEmbedder(), str(tmp_path))

        assert manifest["pdf"] == ["v1.pdf"]  # did succeed, despite the lock left by the "dead container"
