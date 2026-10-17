"""Validation, safe naming and registry for documents uploaded by a user
from the Library — everything that precedes indexing itself (see
index_builder.py for the FAISS rebuild).

Pure Python, no dependency on Modal or FastAPI: testable with a simple
temporary directory (see tests/test_document_pipeline.py), the same way
rag_engine.py already is with test doubles.
"""

import io
import json
import os
import re
import threading
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

StatutDocument = Literal["UPLOADED", "EXTRACTING", "INDEXING", "READY", "FAILED", "DELETING"]

TAILLE_MAX_OCTETS_DEFAUT = 25 * 1024 * 1024  # 25 MB, configurable (see main.py)
SIGNATURE_PDF = b"%PDF-"


class FichierInvalide(Exception):
    """Message ALWAYS non-sensitive (never a disk path, never file
    content): exposed as-is to the client as message_erreur."""


def valider_fichier_pdf(contenu: bytes, nom_original: str, taille_max_octets: int = TAILLE_MAX_OCTETS_DEFAUT) -> None:
    """REAL checks (not just the extension): size, PDF binary signature,
    structure readable by pypdf, not encrypted, at least one page.
    Raises FichierInvalide with a precise reason if any of these checks
    fails.
    """
    if not nom_original.lower().endswith(".pdf"):
        raise FichierInvalide("Only .pdf files are accepted.")

    if len(contenu) == 0:
        raise FichierInvalide("The file is empty.")

    if len(contenu) > taille_max_octets:
        raise FichierInvalide(f"File too large (max {taille_max_octets // (1024 * 1024)} MB).")

    # Real binary signature (the "MIME type" declared by the browser is
    # never trustworthy): a genuine PDF starts with "%PDF-", wherever it
    # appears within the first ~1024 bytes (some tools prepend a preamble).
    if SIGNATURE_PDF not in contenu[:1024]:
        raise FichierInvalide("The file content is not a valid PDF (signature missing).")

    try:
        lecteur = PdfReader(io.BytesIO(contenu))
    except PdfReadError as exc:
        raise FichierInvalide("The PDF file is corrupted or unreadable.") from exc

    if lecteur.is_encrypted:
        raise FichierInvalide("Encrypted PDF files are not accepted.")

    if len(lecteur.pages) == 0:
        raise FichierInvalide("The PDF contains no pages.")


_CARACTERES_SURS = re.compile(r"[^A-Za-z0-9._ -]")


def nom_affichage_securise(nom_original: str) -> str:
    """Sanitizes the ORIGINAL name for safe display (never used as a disk
    path — see generer_id_document for the actual storage name). Strips
    any path separator and control characters."""
    nom = unicodedata.normalize("NFKC", nom_original)
    nom = os.path.basename(nom)  # strips any "../" or "/..." supplied by the client
    nom = _CARACTERES_SURS.sub("_", nom)
    nom = nom.strip(" ._") or "document.pdf"
    return nom[:200]


def generer_id_document() -> str:
    return uuid.uuid4().hex


def calculer_sha256(contenu: bytes) -> str:
    import hashlib

    return hashlib.sha256(contenu).hexdigest()


@dataclass
class EnregistrementDocument:
    id: str
    nom_original: str
    nom_stocke: str  # "<id>.pdf" — never derived from the user-supplied name
    taille_octets: int
    hash_sha256: str
    nb_pages: int = 0
    nb_passages: int = 0
    date_ajout: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    statut: StatutDocument = "UPLOADED"
    message_erreur: Optional[str] = None


class DocumentRegistry:
    """Persists the list of managed documents (registry.json) in the
    store's root directory (a Modal Volume in production, a local folder
    in tests). An in-memory lock guards against concurrent writes WITHIN
    THIS PROCESS; on Modal, the volume must be committed after every write
    (see modal_app.py) for other containers to see the changes."""

    def __init__(self, racine: str) -> None:
        self.racine = racine
        self.chemin_registry = os.path.join(racine, "registry.json")
        self._verrou = threading.Lock()
        os.makedirs(racine, exist_ok=True)

    def _lire(self) -> dict[str, dict]:
        if not os.path.isfile(self.chemin_registry):
            return {}
        with open(self.chemin_registry, encoding="utf-8") as f:
            return json.load(f)

    def _ecrire(self, donnees: dict[str, dict]) -> None:
        chemin_tmp = self.chemin_registry + ".tmp"
        with open(chemin_tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(chemin_tmp, self.chemin_registry)  # atomic write

    def ajouter(self, enregistrement: EnregistrementDocument) -> None:
        with self._verrou:
            donnees = self._lire()
            donnees[enregistrement.id] = asdict(enregistrement)
            self._ecrire(donnees)

    def mettre_a_jour(self, id_document: str, **champs) -> None:
        with self._verrou:
            donnees = self._lire()
            if id_document not in donnees:
                raise KeyError(f"Document {id_document!r} not found in the registry.")
            donnees[id_document].update(champs)
            self._ecrire(donnees)

    def supprimer(self, id_document: str) -> None:
        with self._verrou:
            donnees = self._lire()
            donnees.pop(id_document, None)
            self._ecrire(donnees)

    def obtenir(self, id_document: str) -> Optional[dict]:
        return self._lire().get(id_document)

    def lister(self) -> list[dict]:
        return list(self._lire().values())

    def trouver_par_hash(self, hash_sha256: str) -> Optional[dict]:
        for doc in self._lire().values():
            if doc["hash_sha256"] == hash_sha256 and doc["statut"] != "DELETING":
                return doc
        return None

    def chemin_pdf(self, enregistrement_ou_id) -> str:
        nom_stocke = (
            enregistrement_ou_id["nom_stocke"]
            if isinstance(enregistrement_ou_id, dict)
            else self.obtenir(enregistrement_ou_id)["nom_stocke"]
        )
        return os.path.join(self.racine, "documents", nom_stocke)
