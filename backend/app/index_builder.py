"""Atomic rebuild of the FAISS index, from:
- "historical" chunks (documents indexed before this feature existed,
  whose original PDF was never available on this volume — only their
  already-extracted text is kept, never re-extracted);
- PDFs actually stored on the document volume (document_pipeline.py),
  re-extracted on every rebuild.

Never a direct replacement: a temporary version is built, validated, then
atomically swapped in (os.replace, atomic on a single POSIX filesystem —
so on the same Modal volume). The old version becomes "previous" (rollback
possible), never deleted right away.

NEVER imports torch/transformers/Qwen: only uses an already-loaded
embedder (BGE-M3 on CPU), passed in as a parameter — see app/rag_engine.py.
"""

import asyncio
import errno
import json
import os
import shutil
from datetime import datetime, timezone

TAILLE_PASSAGE = 800
CHEVAUCHEMENT = 150
# Real bug encountered in production: calling embedder.encode() on ALL
# passages at once (e.g. 1489) holds the GIL long enough to freeze the
# whole container (no more requests served) — Modal eventually replaced
# it, killing the task mid-way (document stuck in INDEXING, rebuild lock
# never released). Encoding in small batches, with an explicit yield to
# the event loop between each batch, lets the server keep answering other
# requests in the meantime.
TAILLE_LOT_EMBEDDING = 64

NOM_LOCK = ".reindex.lock"
DOSSIER_COURANT = "current"
DOSSIER_PRECEDENT = "previous"
DIMENSION_BGE_M3 = 1024  # used ONLY when chunks is empty (see below):
# we avoid calling embedder.encode([]), whose actual behavior
# (sentence_transformers model) was never verified for an empty list.


class ReconstructionDejaEnCours(Exception):
    pass


class IndexInvalide(Exception):
    """Raised if the built temporary version fails validation — in that
    case, "current" is NEVER touched (see reconstruire_index)."""


def decouper_texte(texte: str, taille: int = TAILLE_PASSAGE, chevauchement: int = CHEVAUCHEMENT) -> list[str]:
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def extraire_chunks_pdf(chemin_pdf: str, nom_source_affiche: str) -> list[dict]:
    """nom_source_affiche: the ORIGINAL name (not the internal storage
    name) — this is what the user and citations must see."""
    from pypdf import PdfReader

    chunks = []
    lecteur = PdfReader(chemin_pdf)
    position = 0
    for indice_page, page in enumerate(lecteur.pages):
        texte_page = page.extract_text() or ""
        for morceau in decouper_texte(texte_page):
            chunks.append(
                {"source": nom_source_affiche, "page": indice_page + 1, "texte": morceau, "position": position}
            )
            position += 1
    return chunks


AGE_MAX_VERROU_SECONDES = 15 * 60  # see _verrou_est_perime below


def _verrou_est_perime(chemin: str) -> bool:
    """A container killed/recycled mid-processing (e.g. a real incident
    encountered in production before switching to batched encoding) leaves
    the lock orphaned forever, blocking ANY future rebuild. A lock older
    than AGE_MAX_VERROU_SECONDES is considered abandoned and can be
    reclaimed — well above the time a normal rebuild now takes."""
    try:
        with open(chemin, encoding="utf-8") as f:
            horodatage = datetime.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return True  # unreadable/corrupted: we don't let it block forever
    age = datetime.now(timezone.utc) - horodatage
    return age.total_seconds() > AGE_MAX_VERROU_SECONDES


class VerrouReconstruction:
    """Per-file lock (O_CREAT|O_EXCL, atomic at the filesystem level):
    prevents two simultaneous rebuilds, including across different
    processes/containers sharing the same volume."""

    def __init__(self, racine: str) -> None:
        self.chemin = os.path.join(racine, NOM_LOCK)

    def __enter__(self) -> "VerrouReconstruction":
        try:
            fd = os.open(self.chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(datetime.now(timezone.utc).isoformat()).encode("utf-8"))
            os.close(fd)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                if _verrou_est_perime(self.chemin):
                    os.remove(self.chemin)
                    return self.__enter__()  # one retry only: restarts with a fresh lock
                raise ReconstructionDejaEnCours(
                    "An index rebuild is already in progress — try again shortly."
                ) from exc
            raise
        return self

    def __exit__(self, *_exc) -> None:
        try:
            os.remove(self.chemin)
        except FileNotFoundError:
            pass


def _valider_dossier_index(dossier: str) -> None:
    """Actually loads the 3 files (not just checking they exist): it's the
    only way to detect a truncated or corrupted index before making it
    active."""
    import faiss

    for nom in ("index.faiss", "chunks.json", "manifest.json"):
        chemin = os.path.join(dossier, nom)
        if not os.path.isfile(chemin):
            raise IndexInvalide(f"Missing file after build: {nom}")

    try:
        index = faiss.read_index(os.path.join(dossier, "index.faiss"))
        with open(os.path.join(dossier, "chunks.json"), encoding="utf-8") as f:
            chunks = json.load(f)
        with open(os.path.join(dossier, "manifest.json"), encoding="utf-8") as f:
            json.load(f)
    except Exception as exc:  # noqa: BLE001 — any corruption must be rejected
        raise IndexInvalide(f"Rebuilt index is invalid: {exc}") from exc

    if index.ntotal != len(chunks):
        raise IndexInvalide(
            f"Inconsistency: {index.ntotal} FAISS vectors for {len(chunks)} declared passages."
        )


async def _encoder_par_lots(embedder, textes: list[str]):
    """Encodes in several SHORT calls (TAILLE_LOT_EMBEDDING passages at a
    time), each delegated to a thread (asyncio.to_thread) with an explicit
    yield point between batches — never one giant encode() call that holds
    the GIL for several minutes straight (see the comment on
    TAILLE_LOT_EMBEDDING)."""
    import numpy as np

    morceaux = []
    for debut in range(0, len(textes), TAILLE_LOT_EMBEDDING):
        lot = textes[debut : debut + TAILLE_LOT_EMBEDDING]
        embeddings_lot = await asyncio.to_thread(
            embedder.encode, lot, convert_to_numpy=True, normalize_embeddings=True
        )
        morceaux.append(embeddings_lot)
        await asyncio.sleep(0)  # explicitly yields control back to the event loop
    return np.concatenate(morceaux, axis=0)


async def reconstruire_index(
    chunks_historiques: list[dict],
    documents_actifs: list[dict],
    registry,
    embedder,
    racine_store: str,
) -> dict:
    """documents_actifs: registry records (status != DELETING/FAILED) to
    re-extract from their stored PDF. Returns the new manifest.

    Protected by VerrouReconstruction: raises ReconstructionDejaEnCours if
    another call is already in progress (see main.py, which turns this
    into a 409).

    ASYNC (not just by convention): see _encoder_par_lots — this is what
    lets the server keep answering other requests WHILE a rebuild is
    running, instead of freezing the whole container."""
    dossier_index = os.path.join(racine_store, "index")
    os.makedirs(dossier_index, exist_ok=True)

    with VerrouReconstruction(dossier_index):
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        dossier_temp = os.path.join(dossier_index, f"building-{horodatage}")
        os.makedirs(dossier_temp, exist_ok=True)

        try:
            chunks = list(chunks_historiques)
            hashes_pdf: dict[str, str] = {}
            stats_par_pdf: dict[str, dict] = {}

            for doc in documents_actifs:
                chemin_pdf = registry.chemin_pdf(doc)
                # Also delegated to a thread: several large PDFs could
                # otherwise delay yielding to the event loop, even though
                # it's rarely the dominant factor.
                nouveaux = await asyncio.to_thread(extraire_chunks_pdf, chemin_pdf, doc["nom_original"])
                chunks.extend(nouveaux)
                hashes_pdf[doc["nom_original"]] = doc["hash_sha256"]
                stats_par_pdf[doc["nom_original"]] = {
                    "pages": doc["nb_pages"],
                    "passages": len(nouveaux),
                }
                registry.mettre_a_jour(doc["id"], nb_passages=len(nouveaux))

            # An empty chunks list is a LEGITIMATE state (e.g. deleting the
            # last managed document, with no historical document) —
            # produces a 0-vector FAISS index, not an error. rag_engine.py
            # knows how to handle a search on an empty index (see
            # _rechercher_passages).
            import faiss

            if chunks:
                textes = [c["texte"] for c in chunks]
                embeddings = (await _encoder_par_lots(embedder, textes)).astype("float32")
                index = faiss.IndexFlatIP(embeddings.shape[1])
                index.add(embeddings)
            else:
                index = faiss.IndexFlatIP(DIMENSION_BGE_M3)

            faiss.write_index(index, os.path.join(dossier_temp, "index.faiss"))
            with open(os.path.join(dossier_temp, "chunks.json"), "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)

            manifest = {
                "date_creation": datetime.now(timezone.utc).isoformat(),
                "modele_embeddings": "BAAI/bge-m3",
                "pdf": sorted({c["source"] for c in chunks}),
                "hashes_pdf": hashes_pdf,
                "stats_par_pdf": stats_par_pdf,
            }
            with open(os.path.join(dossier_temp, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            _valider_dossier_index(dossier_temp)

            # Atomic swap: the old "current" version becomes "previous"
            # (rollback possible), never deleted directly.
            dossier_courant = os.path.join(dossier_index, DOSSIER_COURANT)
            dossier_precedent = os.path.join(dossier_index, DOSSIER_PRECEDENT)
            if os.path.isdir(dossier_courant):
                if os.path.isdir(dossier_precedent):
                    shutil.rmtree(dossier_precedent)
                os.replace(dossier_courant, dossier_precedent)
            os.replace(dossier_temp, dossier_courant)

            return manifest
        except Exception:
            shutil.rmtree(dossier_temp, ignore_errors=True)
            raise


def rollback_vers_version_precedente(racine_store: str) -> bool:
    """Returns False if no previous version exists (nothing to do)."""
    dossier_index = os.path.join(racine_store, "index")
    os.makedirs(dossier_index, exist_ok=True)
    dossier_courant = os.path.join(dossier_index, DOSSIER_COURANT)
    dossier_precedent = os.path.join(dossier_index, DOSSIER_PRECEDENT)

    with VerrouReconstruction(dossier_index):
        if not os.path.isdir(dossier_precedent):
            return False
        if os.path.isdir(dossier_courant):
            shutil.rmtree(dossier_courant)
        os.replace(dossier_precedent, dossier_courant)
        return True


def chemin_index_courant(racine_store: str) -> str:
    return os.path.join(racine_store, "index", DOSSIER_COURANT)
