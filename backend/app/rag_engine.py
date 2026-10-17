"""Multi-PDF RAG engine, used by the FastAPI API.

Reuses EXACTLY the safety mechanism validated in
scripts/query_document_index.py (claims + double verification
citation-present / SUPPORTED-NOT_SUPPORTED), refactored into a class to:
- load the index, the embedder and Qwen ONLY ONCE per container
  (called from FastAPI's "lifespan", see main.py);
- answer multiple questions without reloading anything;
- behave properly in the ABSENCE of a GPU (e.g. on this Mac, which has no
  CUDA): the engine stays "degraded" instead of crashing, which gives the
  "backend unavailable" scenario tested in tests/test_backend_unavailable.py.
"""

import json
import os
import re
import threading
import unicodedata
from typing import Optional

INDEX_DIR_DEFAULT = os.environ.get("INDEX_DIR", "data/indexes/aftech_documents")

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# Real bug diagnosed in production (see logs "[rag_engine] no AFFIRMATION
# parsed"): for certain questions/languages, Qwen adds an introductory
# prose paragraph BEFORE the requested structured block — with 400 tokens,
# this preamble alone could exhaust the budget before the end of the
# CITATION (cut off without a closing quote), making the whole block
# unreadable by PATTERN_AFFIRMATION despite a genuine attempt and a
# faithful citation. 900 leaves enough margin even with such a preamble +
# a long citation (up to CITATION_MAX_CARACTERES).
MAX_NEW_TOKENS = 900
CITATION_MAX_CARACTERES = 200

LANGUES_SUPPORTEES = ("fr", "en", "de")

# One "not found" sentence per response language (response_language) —
# never an on-the-fly automatic translation: the text is fixed and
# validated for each language, just as REPONSE_NON_TROUVEE already was for
# French.
REPONSE_NON_TROUVEE_PAR_LANGUE = {
    "fr": "Information non trouvée dans les documents.",
    "en": "Information not found in the documents.",
    "de": "Information in den Dokumenten nicht gefunden.",
}
REPONSE_NON_TROUVEE = REPONSE_NON_TROUVEE_PAR_LANGUE["fr"]

# "[source: file, page N]" suffix added after each validated claim — never
# translated: the file name and page label stay neutral/faithful to the
# source, only the connector word ("source"/"source"/"Quelle") changes.
SOURCE_SUFFIXE_PAR_LANGUE = {
    "fr": "[source : {fichier}, page {page}]",
    "en": "[source: {fichier}, page {page}]",
    "de": "[Quelle: {fichier}, Seite {page}]",
}

NOM_LANGUE_PAR_CODE = {"fr": "français", "en": "English", "de": "Deutsch"}

SEUIL_STATUT_COMPLETE = 3


def construire_system_prompt(langue: str) -> str:
    """System prompt, parameterized by the requested RESPONSE language.

    NOTE (presentation build): the prompt text below is intentionally left
    in French — it is sent as-is to the LLM and was carefully tuned/fixed
    against real production bugs throughout this project's history.
    Translating it would be a behavioral change, not a pure translation, and
    could not be re-verified without a live GPU deployment. Everything
    else in this codebase (comments, docstrings, API-facing error strings)
    has been translated to English; this prompt body is the one deliberate
    exception.

    The CITATION must always remain an exact copy of the source passage, so
    in its ORIGINAL language, even when the response language differs —
    this is made explicit below so Qwen never "translates" a citation."""
    nom_langue = NOM_LANGUE_PAR_CODE[langue]
    reponse_non_trouvee = REPONSE_NON_TROUVEE_PAR_LANGUE[langue]
    return (
        f"Tu es un assistant documentaire. Tu réponds TOUJOURS en {nom_langue}, "
        "quelle que soit la langue des passages fournis ou de la question : "
        "traduis le SENS de ta réponse (l'AFFIRMATION) en cette langue si "
        "besoin. Les passages fournis peuvent provenir de documents "
        "différents et sont identifiés par P1, P2, P3, etc. Tu dois répondre "
        "UNIQUEMENT à partir de ces passages. Ne complète jamais avec tes "
        "connaissances générales, même si tu penses connaître la réponse.\n\n"
        "Si les passages ne contiennent pas clairement la réponse, réponds "
        f'uniquement avec la phrase exacte : "{reponse_non_trouvee}" (rien d\'autre).\n\n'
        "Sinon, découpe ta réponse en affirmations séparées : une seule affirmation "
        "pour une réponse simple, ou une affirmation distincte par élément si la "
        "réponse est une liste ou une synthèse à plusieurs points (6 éléments "
        "maximum). Ne commence JAMAIS par un paragraphe d'introduction, un résumé "
        "ou une reformulation de la question avant le bloc structuré : ta toute "
        "première ligne doit être \"AFFIRMATION:\". Pour CHAQUE affirmation, "
        "utilise STRICTEMENT ce format, sur 4 lignes :\n"
        f"AFFIRMATION: <une seule affirmation, phrase complète, en {nom_langue}>\n"
        "PASSAGE: <identifiant, ex. P2>\n"
        "PAGE: <numéro de page>\n"
        f'CITATION: "<citation copiée EXACTEMENT depuis ce passage, dans sa langue '
        f"D'ORIGINE (ne la traduis jamais), {CITATION_MAX_CARACTERES} "
        'caractères maximum>"\n\n'
        "Répète ce bloc de 4 lignes pour chaque affirmation. Termine toujours tes phrases.\n\n"
        "Cas particulier important : si la question demande QUEL document, fichier "
        "ou passage traite d'un sujet (par exemple \"quel document parle de X ?\"), "
        "ne réponds PAS \"non trouvée\" simplement parce qu'aucune phrase ne dit "
        "littéralement \"ce document parle de X\" — il suffit qu'un passage "
        "contienne clairement des informations sur ce sujet pour que tu puisses "
        "répondre. Dans ce cas, formule l'AFFIRMATION comme une information "
        "concrète tirée de ce passage (pas besoin de deviner ou de répéter le nom "
        "du fichier : il sera ajouté automatiquement à partir du passage cité)."
    )


# Kept for compatibility (existing tests, scripts): default prompt in
# French — identical to construire_system_prompt("fr").
SYSTEM_PROMPT = construire_system_prompt("fr")

# NOTE (presentation build): same exception as above — sent as-is to the
# LLM, left untranslated on purpose.
VERIFICATEUR_SYSTEM_PROMPT = (
    "Tu es un vérificateur strict. Tu reçois une question, une affirmation et une "
    "citation censée prouver cette affirmation. Réponds par un seul mot : "
    "SUPPORTED si la citation prouve clairement l'affirmation pour cette question, "
    "ou NOT_SUPPORTED si ce n'est pas le cas ou si c'est ambigu. N'écris rien d'autre."
)

CARACTERES_INVISIBLES = "­​‌‍⁠﻿"


def normalize_text(texte: str) -> str:
    """Same normalization as scripts/pdf_assistant.py /
    query_document_index.py: NFKC, non-breaking spaces, invisible
    characters, literal "\\n" sequences and real newlines, multiple
    spaces, lowercase."""
    texte = unicodedata.normalize("NFKC", texte)
    texte = texte.replace(" ", " ").replace(" ", " ")

    for caractere in CARACTERES_INVISIBLES:
        texte = texte.replace(caractere, "")

    texte = texte.replace("\\n", " ")
    texte = texte.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texte = " ".join(texte.split())

    return texte.lower()


# CITATION ends with a closing quote OR the end of the text (\Z): a safety
# net in case generation gets cut off by MAX_NEW_TOKENS before the closing
# quote (real bug diagnosed in production — see MAX_NEW_TOKENS above). A
# truncated citation remains a faithful PREFIX of the source passage:
# citation_presente (exact substring check) still validates it correctly,
# instead of losing the whole block for want of a closing quote.
PATTERN_AFFIRMATION = re.compile(
    r"AFFIRMATION\s*:\s*(?P<affirmation>.+?)\s*"
    r"PASSAGE\s*:\s*(?P<passage_id>\S+)\s*"
    r"PAGE\s*:\s*(?P<page>\d+)\s*"
    r'CITATION\s*:\s*"(?P<citation>.+?)(?:"|\Z)',
    re.IGNORECASE | re.DOTALL,
)


def parser_affirmations(texte_brut: str) -> list[dict]:
    return [
        {
            "affirmation": m.group("affirmation").strip(),
            "passage_id": m.group("passage_id").strip().upper(),
            "page": int(m.group("page")),
            "citation": m.group("citation").strip(),
        }
        for m in PATTERN_AFFIRMATION.finditer(texte_brut)
    ]


class BackendUnavailable(Exception):
    """The RAG engine cannot answer (no GPU, model not loaded, index
    missing). Translated into HTTP 503 by the API — never an opaque 500."""


class RagEngine:
    def __init__(self, index_dir: str = INDEX_DIR_DEFAULT) -> None:
        self.index_dir = index_dir
        self.ready = False
        self.error: Optional[str] = None
        self.gpu_name = "unavailable"
        self.vram_totale_octets: Optional[int] = None

        self.index = None
        self.chunks: list[dict] = []
        self.manifest: dict = {}
        self.embedder = None
        self.tokenizer = None
        self.model = None

        # Load time per phase (seconds), filled in by _load_impl().
        # Reused by scripts/gpu_benchmark.py to avoid duplicating the
        # loading logic (so: same code = same parameters guaranteed across
        # the GPUs being tested).
        self.timings_chargement: dict[str, float] = {}
        self._verrou_rechargement = threading.Lock()

    # --- Loading (once per container, see main.py:lifespan) ---

    def load(self) -> None:
        """NEVER raises: the server must start even if a package is missing
        or the index is absent, switching to "degraded" mode with a clear
        message (see self.error) instead of crashing."""
        try:
            self._load_impl()
        except Exception as exc:  # noqa: BLE001 — deliberate, see docstring
            self.error = f"Failed to load the RAG engine: {exc}"
            self.ready = False

    def _load_impl(self) -> None:
        import time as _time

        import faiss

        debut = _time.perf_counter()
        try:
            self.index = faiss.read_index(os.path.join(self.index_dir, "index.faiss"))
            with open(os.path.join(self.index_dir, "chunks.json"), encoding="utf-8") as f:
                self.chunks = json.load(f)
            with open(os.path.join(self.index_dir, "manifest.json"), encoding="utf-8") as f:
                self.manifest = json.load(f)
        except FileNotFoundError as exc:
            self.error = f"Index not found in {self.index_dir}: {exc}"
            return
        self.timings_chargement["index_secondes"] = _time.perf_counter() - debut

        import torch
        from sentence_transformers import SentenceTransformer

        debut = _time.perf_counter()
        self.embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
        self.timings_chargement["embedder_secondes"] = _time.perf_counter() - debut

        if not torch.cuda.is_available():
            self.error = (
                "No CUDA GPU detected on this machine: the generation model "
                "(Qwen, 4-bit quantized) cannot be loaded here. Document "
                "search and /health remain available; /ask will return 503 "
                "until deployed on a GPU machine (Modal)."
            )
            return

        self.gpu_name = torch.cuda.get_device_name(0)
        self.vram_totale_octets = torch.cuda.get_device_properties(0).total_memory

        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        if "T4" in self.gpu_name:
            compute_dtype = torch.float16
        elif torch.cuda.is_bf16_supported():
            compute_dtype = torch.bfloat16
        else:
            compute_dtype = torch.float16

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )

        debut = _time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL_NAME,
            quantization_config=quant_config,
            device_map="auto",
        )
        self.timings_chargement["llm_secondes"] = _time.perf_counter() - debut

        self.ready = True

    # --- State (used by /health and /documents, never blocking) ---

    def health(self) -> dict:
        vram_utilisee_octets = None
        if self.ready:
            import torch

            vram_utilisee_octets = torch.cuda.memory_allocated()

        return {
            "status": "ok" if self.ready else "degraded",
            "ready": self.ready,
            "llm_model": LLM_MODEL_NAME,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "gpu": self.gpu_name,
            "vram_totale_octets": self.vram_totale_octets,
            "vram_utilisee_octets": vram_utilisee_octets,
            "documents_count": len(self.manifest.get("pdf", [])),
            "chunks_count": len(self.chunks),
        }

    def recharger_index(self, dossier_index: str) -> None:
        """Replaces the ACTIVE index/chunks/manifest with a successfully
        rebuilt version (see index_builder.reconstruire_index) — without
        reloading Qwen or BGE-M3, and without restarting the container.
        Searches already in flight at call time keep using the old version
        (see _rechercher_passages, which captures its own local
        references)."""
        import faiss

        nouvel_index = faiss.read_index(os.path.join(dossier_index, "index.faiss"))
        with open(os.path.join(dossier_index, "chunks.json"), encoding="utf-8") as f:
            nouveaux_chunks = json.load(f)
        with open(os.path.join(dossier_index, "manifest.json"), encoding="utf-8") as f:
            nouveau_manifest = json.load(f)

        with self._verrou_rechargement:
            self.index = nouvel_index
            self.chunks = nouveaux_chunks
            self.manifest = nouveau_manifest

    def chunks_historiques(self, noms_affiches_geres: set[str]) -> list[dict]:
        """Currently active chunks whose source is NOT managed by the
        document registry (e.g. the 4 PDFs already indexed before this
        feature existed, whose original file was never on this volume) —
        kept as-is during a rebuild, never re-extracted since we don't have
        their source PDF."""
        return [c for c in self.chunks if c["source"] not in noms_affiches_geres]

    def documents(self) -> list[dict]:
        stats = self.manifest.get("stats_par_pdf", {})
        hashes = self.manifest.get("hashes_pdf", {})
        date_index = self.manifest.get("date_creation", "")
        modele = self.manifest.get("modele_embeddings", EMBEDDING_MODEL_NAME)

        return [
            {
                "nom_fichier": nom,
                "pages": stats.get(nom, {}).get("pages", 0),
                "passages": stats.get(nom, {}).get("passages", 0),
                "hash_sha256": hashes.get(nom, ""),
                "modele_embeddings": modele,
                "date_index": date_index,
            }
            for nom in self.manifest.get("pdf", [])
        ]

    # --- Search + generation ---

    def _rechercher_passages(self, question: str, top_k: int) -> list[dict]:
        # LOCAL references captured once: if recharger_index() replaces
        # self.index/self.chunks while this search is running (a document
        # added from the Library), this call keeps using the version it
        # captured at the start — never a mix of the two.
        index, chunks = self.index, self.chunks

        embedding_question = self.embedder.encode(
            [question], convert_to_numpy=True, normalize_embeddings=True
        ).astype("float32")

        nb = min(top_k, len(chunks))
        if nb == 0:
            # Empty library (every document deleted): FAISS refuses k=0
            # (AssertionError), so we short-circuit instead of querying an
            # index with no vectors at all.
            return []
        scores, indices = index.search(embedding_question, nb)

        resultats = []
        for rang, (score, indice) in enumerate(zip(scores[0], indices[0])):
            if indice < 0:
                continue
            chunk = chunks[indice]
            resultats.append(
                {
                    "id": f"P{rang + 1}",
                    "texte": chunk["texte"],
                    "source": chunk["source"],
                    "page": chunk["page"],
                    "score": float(score),
                }
            )
        return resultats

    def _construire_prompt(self, question: str, passages: list[dict]) -> str:
        # NOTE (presentation build): scaffolding text sent to the LLM, left
        # untranslated on purpose — see construire_system_prompt's docstring.
        contexte = "\n\n".join(
            f"[{p['id']} | fichier {p['source']} | page {p['page']}] {p['texte']}" for p in passages
        )
        return f"Passages :\n{contexte}\n\nQuestion : {question}"

    def _generer_texte(self, messages: list[dict], max_new_tokens: int) -> tuple[str, int, int]:
        """Returns (generated_text, nb_input_tokens, nb_generated_tokens).

        The token counters are exposed for the GPU benchmark
        (scripts/gpu_benchmark.py); main.py simply ignores them (Pydantic
        only keeps the fields declared on AskResponse)."""
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)

        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

        nb_tokens_entree = inputs["input_ids"].shape[-1]
        generated_ids = output_ids[0][nb_tokens_entree:]
        texte = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        return texte, nb_tokens_entree, len(generated_ids)

    def _verifier_affirmation(self, question: str, affirmation: str, citation: str) -> bool:
        messages = [
            {"role": "system", "content": VERIFICATEUR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question : {question}\n"
                    f"Affirmation : {affirmation}\n"
                    f'Citation : "{citation}"'
                ),
            },
        ]
        verdict_brut, _, _ = self._generer_texte(messages, max_new_tokens=10)
        verdict_brut = verdict_brut.strip().upper()

        if "NOT_SUPPORTED" in verdict_brut:
            return False
        return "SUPPORTED" in verdict_brut

    def ask(self, question: str, top_k: int = 8, response_language: str = "fr") -> dict:
        if not self.ready:
            raise BackendUnavailable(self.error or "RAG engine not ready.")
        if response_language not in LANGUES_SUPPORTEES:
            raise ValueError(f"Unsupported response language: {response_language!r}")

        import time

        debut_recherche = time.perf_counter()
        passages = self._rechercher_passages(question, top_k)
        temps_recherche = time.perf_counter() - debut_recherche

        passages_par_id = {p["id"]: p for p in passages}

        debut_generation = time.perf_counter()
        messages = [
            {"role": "system", "content": construire_system_prompt(response_language)},
            {"role": "user", "content": self._construire_prompt(question, passages)},
        ]
        reponse_brute, nb_tokens_entree, nb_tokens_generes = self._generer_texte(messages, MAX_NEW_TOKENS)

        affirmations = parser_affirmations(reponse_brute)
        for aff in affirmations:
            passage = passages_par_id.get(aff["passage_id"])
            citation_presente = bool(passage) and bool(aff["citation"].strip())
            if citation_presente:
                citation_presente = normalize_text(aff["citation"]) in normalize_text(passage["texte"])

            aff["citation_presente"] = citation_presente
            aff["preuve_supported"] = (
                self._verifier_affirmation(question, aff["affirmation"], aff["citation"])
                if citation_presente
                else False
            )
            aff["affirmation_validee"] = aff["citation_presente"] and aff["preuve_supported"]

            # File/page come from OUR OWN search metadata, never from the
            # text Qwen generated: we don't trust the model on this point.
            aff["fichier"] = passage["source"] if passage else None
            aff["page"] = passage["page"] if passage else aff["page"]

            if not aff["affirmation_validee"]:
                # PERMANENT diagnostic (not a probe to remove later): a
                # claim rejected despite a genuine attempt by Qwen is
                # precisely the hardest case to debug without this — this
                # text is normally never seen (the API only returns
                # validated claims). Nothing sensitive: just text generated
                # by the model from an already-indexed document.
                print(
                    "[rag_engine] claim rejected — "
                    f"language={response_language!r} passage_id={aff['passage_id']!r} "
                    f"citation_presente={citation_presente} "
                    f"preuve_supported={aff['preuve_supported']} "
                    f"affirmation={aff['affirmation']!r} "
                    f"citation={aff['citation']!r}"
                )
        if not affirmations:
            print(
                f"[rag_engine] no AFFIRMATION parsed — language={response_language!r} "
                f"raw_response={reponse_brute!r}"
            )

        temps_generation = time.perf_counter() - debut_generation

        validees = [a for a in affirmations if a["affirmation_validee"]]
        suffixe_source = SOURCE_SUFFIXE_PAR_LANGUE[response_language]

        if not validees:
            answer = REPONSE_NON_TROUVEE_PAR_LANGUE[response_language]
            statut = "NOT_FOUND"
        elif len(validees) == 1:
            a = validees[0]
            answer = f"{a['affirmation']} {suffixe_source.format(fichier=a['fichier'], page=a['page'])}"
            statut = "COMPLETE"
        else:
            answer = "\n".join(
                f"- {a['affirmation']} {suffixe_source.format(fichier=a['fichier'], page=a['page'])}"
                for a in validees
            )
            statut = "COMPLETE" if len(validees) >= SEUIL_STATUT_COMPLETE else "PARTIAL"

        sources = [
            {
                "fichier": p["source"],
                "page": p["page"],
                "extrait": p["texte"][:200],
                "score": p["score"],
            }
            for p in passages
        ]

        return {
            "answer": answer,
            "status": statut,
            "sources": sources,
            "validated_claims": [
                {
                    "affirmation": a["affirmation"],
                    "fichier": a["fichier"],
                    "page": a["page"],
                    "citation": a["citation"],
                    "citation_presente": a["citation_presente"],
                    "preuve_supported": a["preuve_supported"],
                }
                for a in validees
            ],
            "timings": {
                "recherche_secondes": temps_recherche,
                "generation_secondes": temps_generation,
                "total_secondes": temps_recherche + temps_generation,
            },
            # Extra fields (not part of AskResponse -> ignored by the API,
            # used by scripts/gpu_benchmark.py).
            "tokens_entree": nb_tokens_entree,
            "tokens_generes": nb_tokens_generes,
        }


# --- Lock-protected singleton: prevents two simultaneous loads ---
# (explicit requirement: "prevent two simultaneous loads of the model").
# In practice, it's mostly FastAPI's "lifespan" (see main.py) that calls
# load() once; this lock guards against an accidental double call (e.g.
# tests, hot-reload in dev).
_engine: Optional[RagEngine] = None
_engine_lock = threading.Lock()


def get_engine(index_dir: str = INDEX_DIR_DEFAULT) -> RagEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                engine = RagEngine(index_dir)
                engine.load()
                _engine = engine
    return _engine


def reset_engine_for_tests() -> None:
    """Tests only: forces the next call to get_engine() to start fresh."""
    global _engine
    _engine = None
