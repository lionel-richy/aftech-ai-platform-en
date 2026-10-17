"""
Build (or reuse) a multi-PDF FAISS index for AFTECH.

Unlike pdf_assistant.py (which re-reads and re-embeds a single PDF on every
run), this script builds a REUSABLE index for several PDFs at once:
- index.faiss   : the embeddings of every passage, ready for search
- chunks.json   : the text of each passage + its provenance (file, page)
- manifest.json : metadata (date, model, PDF hashes...) used to know
                  whether the index is still up to date.

If no PDF has changed since the last build, nothing is recomputed:
embeddings are the slowest step, so reusing them is the whole point of
this index.
"""

import argparse
import glob
import hashlib
import json
import os
from datetime import datetime, timezone

import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

TAILLE_PASSAGE = 800  # number of characters per passage (approximate)
CHEVAUCHEMENT = 150  # characters shared between two consecutive passages

DOSSIER_PDF_DEFAUT = "data/documents"
DOSSIER_INDEX_DEFAUT = "data/indexes/aftech_documents"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Builds or reuses a FAISS index from a folder of PDFs."
    )
    # Named options (no positional argument): "colab exec" runs this code in
    # an already-running Jupyter kernel, whose own arguments (e.g. "-f
    # <connection-file>") are visible here. An optional positional argument
    # would capture that path by mistake; a named option can only be filled
    # by "--dossier-pdf ...", which will never happen from the kernel.
    parser.add_argument(
        "--dossier-pdf",
        dest="dossier_pdf",
        default=DOSSIER_PDF_DEFAUT,
        help=f"Folder containing the PDFs to index (default: {DOSSIER_PDF_DEFAUT})",
    )
    parser.add_argument(
        "--index-dir",
        default=DOSSIER_INDEX_DEFAUT,
        help=f"Folder to save/read the index from (default: {DOSSIER_INDEX_DEFAUT})",
    )
    # parse_known_args (not parse_args), for the same reason: the kernel's
    # other arguments (e.g. "-f") are silently ignored.
    args, _ = parser.parse_known_args()
    return args


def decouper_texte(texte, taille=TAILLE_PASSAGE, chevauchement=CHEVAUCHEMENT):
    """Splits a long text into fixed-size passages, with overlap (avoids an
    important sentence being cut in half at the boundary)."""
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def calculer_hash_fichier(chemin):
    """SHA-256 fingerprint of a file: used to detect whether a PDF changed,
    without having to compare its whole text content byte by byte."""
    sha256 = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(8192), b""):
            sha256.update(bloc)
    return sha256.hexdigest()


def charger_manifest_existant(index_dir):
    chemin_manifest = os.path.join(index_dir, "manifest.json")
    if not os.path.isfile(chemin_manifest):
        return None
    with open(chemin_manifest, encoding="utf-8") as f:
        return json.load(f)


def determiner_si_reconstruction_necessaire(manifest_existant, hash_actuels, index_dir):
    """Compares the current PDFs to those from the last built index.

    Returns (rebuild_needed, human_readable_reason).
    """
    fichiers_index = ["index.faiss", "chunks.json", "manifest.json"]
    if any(not os.path.isfile(os.path.join(index_dir, f)) for f in fichiers_index):
        return True, "no existing index (or incomplete)"

    if manifest_existant is None:
        return True, "no existing index"

    hash_precedents = manifest_existant.get("hashes_pdf", {})
    fichiers_actuels = set(hash_actuels)
    fichiers_precedents = set(hash_precedents)

    ajoutes = fichiers_actuels - fichiers_precedents
    supprimes = fichiers_precedents - fichiers_actuels
    modifies = {
        f for f in (fichiers_actuels & fichiers_precedents) if hash_actuels[f] != hash_precedents[f]
    }

    if ajoutes:
        return True, f"new file(s) detected: {sorted(ajoutes)}"
    if supprimes:
        return True, f"file(s) removed: {sorted(supprimes)}"
    if modifies:
        return True, f"file(s) modified: {sorted(modifies)}"
    return False, None


def extraire_chunks(fichiers_pdf):
    """Reads each PDF page by page and splits it into passages ("chunks").

    Each chunk keeps: a unique id, the source file, the real page number
    (starting at 1), the text, and its position within ITS document (useful
    later to find the previous/next passage).
    """
    chunks = []
    stats_par_pdf = {}

    for chemin_pdf in fichiers_pdf:
        nom_fichier = os.path.basename(chemin_pdf)
        prefixe_id = os.path.splitext(nom_fichier)[0]
        lecteur = PdfReader(chemin_pdf)

        position = 0
        for indice_page, page in enumerate(lecteur.pages):
            numero_page = indice_page + 1  # human page numbers start at 1
            texte_page = page.extract_text() or ""

            for morceau in decouper_texte(texte_page):
                chunks.append(
                    {
                        "id": f"{prefixe_id}-{position:04d}",
                        "source": nom_fichier,
                        "page": numero_page,
                        "texte": morceau,
                        "position": position,
                    }
                )
                position += 1

        stats_par_pdf[nom_fichier] = {"pages": len(lecteur.pages), "passages": position}

    return chunks, stats_par_pdf


def construire_index(fichiers_pdf, hash_actuels, index_dir):
    print(f"Extracting text from {len(fichiers_pdf)} PDF(s)...")
    chunks, stats_par_pdf = extraire_chunks(fichiers_pdf)
    print(f"{len(chunks)} passages extracted in total.")
    for nom, stats in stats_par_pdf.items():
        print(f"  - {nom}: {stats['pages']} pages, {stats['passages']} passages")

    print(f"\nLoading embedding model {EMBEDDING_MODEL_NAME} on CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Computing embeddings for all passages (the slowest step)...")
    textes = [chunk["texte"] for chunk in chunks]
    embeddings = embedder.encode(
        textes,
        convert_to_numpy=True,
        normalize_embeddings=True,  # normalized -> dot product = cosine similarity
        show_progress_bar=True,
    ).astype("float32")

    print("Building the FAISS index...")
    index = faiss.IndexFlatIP(embeddings.shape[1])  # IP = dot product (cosine, since normalized)
    index.add(embeddings)

    os.makedirs(index_dir, exist_ok=True)

    faiss.write_index(index, os.path.join(index_dir, "index.faiss"))

    with open(os.path.join(index_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    manifest = {
        "date_creation": datetime.now(timezone.utc).isoformat(),
        "modele_embeddings": EMBEDDING_MODEL_NAME,
        "pdf": sorted(hash_actuels),
        "hashes_pdf": hash_actuels,
        "stats_par_pdf": stats_par_pdf,
    }
    with open(os.path.join(index_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nIndex built and saved in {index_dir}/")


def main():
    args = parse_args()

    fichiers_pdf = sorted(glob.glob(os.path.join(args.dossier_pdf, "*.pdf")))
    if not fichiers_pdf:
        raise SystemExit(f"No PDF found in {args.dossier_pdf}")

    print(f"{len(fichiers_pdf)} PDF(s) found in {args.dossier_pdf}:")
    for chemin in fichiers_pdf:
        print(f"  - {os.path.basename(chemin)}")

    print("\nComputing SHA-256 fingerprints (to detect a PDF change)...")
    hash_actuels = {os.path.basename(p): calculer_hash_fichier(p) for p in fichiers_pdf}

    manifest_existant = charger_manifest_existant(args.index_dir)
    reconstruction, raison = determiner_si_reconstruction_necessaire(
        manifest_existant, hash_actuels, args.index_dir
    )

    if not reconstruction:
        print("Existing index reused.")
        return

    print(f"Rebuilding the index: {raison}")
    construire_index(fichiers_pdf, hash_actuels, args.index_dir)


if __name__ == "__main__":
    main()
