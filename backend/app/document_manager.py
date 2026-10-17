"""Orchestrates the lifecycle of a document uploaded from the Library:
UPLOADED -> EXTRACTING -> INDEXING -> READY (or FAILED), and deletion
(-> DELETING -> rebuild without that document).

Connects document_pipeline.py (validation, registry), index_builder.py
(atomic rebuild) and rag_engine.py (search, hot reload). No dependency on
FastAPI/Modal here — testable with a real RagEngine (test doubles) and a
temporary folder, see tests/test_document_manager.py.
"""

import logging
import os
from typing import Awaitable, Callable, Optional


async def _ne_rien_faire() -> None:
    pass

from . import index_builder
from .document_pipeline import (
    DocumentRegistry,
    EnregistrementDocument,
    FichierInvalide,
    TAILLE_MAX_OCTETS_DEFAUT,
    calculer_sha256,
    generer_id_document,
    nom_affichage_securise,
    valider_fichier_pdf,
)

logger = logging.getLogger("aftech.documents")


class DocumentDejaIndexe(Exception):
    """A document with identical content (same SHA-256) already exists."""

    def __init__(self, enregistrement_existant: dict):
        self.enregistrement_existant = enregistrement_existant
        super().__init__("This document (identical content) is already indexed.")


class DocumentIntrouvable(Exception):
    pass


class DocumentManager:
    def __init__(
        self,
        racine_store: str,
        engine,
        taille_max_octets: int = TAILLE_MAX_OCTETS_DEFAUT,
        on_mutation: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.racine_store = racine_store
        self.engine = engine
        self.taille_max_octets = taille_max_octets
        self.registry = DocumentRegistry(racine_store)
        # Called (and ALWAYS awaited) after every durable write — in
        # production, commits the Modal Volume (see modal_app.py) so writes
        # survive a container restart. No dependency on `modal` here:
        # no-op in local/tests (see main.py).
        self._on_mutation = on_mutation or _ne_rien_faire
        os.makedirs(os.path.join(racine_store, "documents"), exist_ok=True)

    # --- Upload ---

    async def deposer(self, contenu: bytes, nom_original: str) -> EnregistrementDocument:
        """Validates then registers the file (UPLOADED status) — does NOT
        yet start extraction/indexing (see traiter(), called as a
        background task by main.py: the upload request responds quickly).
        async so it can commit the Modal Volume without blocking (see
        _on_mutation)."""
        valider_fichier_pdf(contenu, nom_original, self.taille_max_octets)  # raises FichierInvalide

        hash_sha256 = calculer_sha256(contenu)
        existant = self.registry.trouver_par_hash(hash_sha256)
        if existant is not None:
            raise DocumentDejaIndexe(existant)

        id_document = generer_id_document()
        enregistrement = EnregistrementDocument(
            id=id_document,
            nom_original=nom_affichage_securise(nom_original),
            nom_stocke=f"{id_document}.pdf",
            taille_octets=len(contenu),
            hash_sha256=hash_sha256,
            statut="UPLOADED",
        )

        # Storage name derived ONLY from the server-generated id — never
        # from the user-supplied name (security requirement).
        chemin_pdf = os.path.join(self.racine_store, "documents", enregistrement.nom_stocke)
        with open(chemin_pdf, "wb") as f:
            f.write(contenu)

        self.registry.ajouter(enregistrement)
        await self._on_mutation()
        logger.info("document added id=%s size=%d status=UPLOADED", id_document, len(contenu))
        return enregistrement

    # --- Processing (extraction + indexing), designed to run as a background task ---
    #
    # ASYNC (not just by convention): real bug encountered in production
    # (see index_builder.py) — a giant synchronous task blocked the whole
    # container for several minutes, to the point that Modal replaced it
    # mid-rebuild, leaving a document permanently stuck in INDEXING.
    # Starlette detects that a BackgroundTask is a coroutine and runs it
    # natively on the event loop (see main.py) — this is WHAT lets the
    # internal yield points (index_builder._encoder_par_lots) keep the
    # server responsive.

    async def traiter(self, id_document: str) -> None:
        self.registry.mettre_a_jour(id_document, statut="EXTRACTING")
        try:
            doc = self.registry.obtenir(id_document)
            if doc is None:
                raise DocumentIntrouvable(id_document)

            from pypdf import PdfReader

            chemin_pdf = self.registry.chemin_pdf(doc)
            nb_pages = len(PdfReader(chemin_pdf).pages)
            self.registry.mettre_a_jour(id_document, nb_pages=nb_pages, statut="INDEXING")

            await self._reconstruire_index_complet()

            self.registry.mettre_a_jour(id_document, statut="READY")
            await self._on_mutation()
            logger.info("document indexed id=%s status=READY", id_document)
        except Exception as exc:  # noqa: BLE001 — never a traceback in message_erreur
            logger.warning("indexing failed id=%s", id_document)
            self.registry.mettre_a_jour(id_document, statut="FAILED", message_erreur=str(exc)[:300])
            raise

    async def _reconstruire_index_complet(self) -> None:
        noms_geres = {d["nom_original"] for d in self.registry.lister()}
        chunks_historiques = self.engine.chunks_historiques(noms_geres)
        # INDEXING: the document we just moved into this state (the one
        # being processed); READY: the others already indexed.
        documents_actifs = [d for d in self.registry.lister() if d["statut"] in ("INDEXING", "READY")]

        await index_builder.reconstruire_index(
            chunks_historiques, documents_actifs, self.registry, self.engine.embedder, self.racine_store
        )
        self.engine.recharger_index(index_builder.chemin_index_courant(self.racine_store))

    # --- Deletion ---

    async def supprimer(self, id_document: str) -> None:
        doc = self.registry.obtenir(id_document)
        if doc is None:
            raise DocumentIntrouvable(id_document)

        self.registry.mettre_a_jour(id_document, statut="DELETING")
        try:
            await self._reconstruire_index_complet_sans(id_document)
            chemin_pdf = self.registry.chemin_pdf(doc)
            if os.path.isfile(chemin_pdf):
                os.remove(chemin_pdf)
            self.registry.supprimer(id_document)
            await self._on_mutation()
            logger.info("document deleted id=%s", id_document)
        except Exception:
            self.registry.mettre_a_jour(id_document, statut="FAILED", message_erreur="Deletion failed.")
            raise

    async def _reconstruire_index_complet_sans(self, id_exclu: str) -> None:
        noms_geres = {d["nom_original"] for d in self.registry.lister() if d["id"] != id_exclu}
        chunks_historiques = self.engine.chunks_historiques(noms_geres | {self.registry.obtenir(id_exclu)["nom_original"]})
        documents_actifs = [
            d for d in self.registry.lister() if d["id"] != id_exclu and d["statut"] in ("INDEXING", "READY")
        ]
        await index_builder.reconstruire_index(
            chunks_historiques, documents_actifs, self.registry, self.engine.embedder, self.racine_store
        )
        self.engine.recharger_index(index_builder.chemin_index_courant(self.racine_store))

    # --- Reading ---

    def obtenir_statut(self, id_document: str) -> Optional[dict]:
        return self.registry.obtenir(id_document)

    def lister_tout(self) -> list[dict]:
        """Merges HISTORICAL documents (from engine.documents(), not
        deletable) with those managed by the registry (deletable)."""
        geres = {d["nom_original"] for d in self.registry.lister()}
        historiques = [
            {**d, "supprimable": False} for d in self.engine.documents() if d["nom_fichier"] not in geres
        ]
        geres_formates = [
            {
                "nom_fichier": d["nom_original"],
                "pages": d["nb_pages"],
                "passages": d["nb_passages"],
                "hash_sha256": d["hash_sha256"],
                "modele_embeddings": "BAAI/bge-m3",
                "date_index": d["date_ajout"],
                "id": d["id"],
                "statut": d["statut"],
                "message_erreur": d.get("message_erreur"),
                "taille_octets": d["taille_octets"],
                "supprimable": True,
            }
            for d in self.registry.lister()
        ]
        return historiques + geres_formates
