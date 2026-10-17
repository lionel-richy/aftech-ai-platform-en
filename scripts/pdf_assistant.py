"""
AFTECH document assistant — PDF version.

Same principle as scripts/document_assistant.py (RAG: Retrieval-Augmented
Generation), but here the knowledge source is a single PDF file instead
of several small .txt files.

This version adds two extra safeguards on top of classic search +
generation:
1) Qwen's answer is split into independent "claims", each with its own
   proof (passage + page + citation);
2) each claim must pass TWO checks before being accepted: does the
   citation really exist in the designated passage, AND does a second
   call to Qwen (which only sees the question, the claim and the
   citation, not the document) confirm that the citation proves the claim.
A claim that fails either check is dropped.

NOTE (presentation build): SYSTEM_PROMPT, VERIFICATEUR_SYSTEM_PROMPT,
REFORMULATION_SYSTEM_PROMPT, REPONSE_NON_TROUVEE, QUESTIONS,
TERMES_DIAGNOSTIC, MOTS_VIDES and MOTS_CLES_LISTE below are left in French
on purpose — they are functional content either sent verbatim to the LLM
or used to match French-language document/question text, sharing the
exact same exception already applied to backend/app/rag_engine.py in
this repo. Everything else (comments, docstrings, CLI/print output) has
been translated to English.
"""

import json
import os
import re
import unicodedata

import torch
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer, util
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# The PDF is already present on the Colab machine at this path
PDF_PATH = "/content/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"

RESULTS_PATH = "results/benchmarks/pdf_rag_test.json"

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# Splitting pages into passages: a page can be long, so it's cut into
# more digestible chunks for similarity search.
TAILLE_PASSAGE = 800  # number of characters per passage (approximate)
CHEVAUCHEMENT = 150  # characters shared between two consecutive passages

# Two-stage search: cast a wide net with semantic similarity alone, then
# refine with a lexical bonus before keeping the final top passages.
TOP_K_INITIAL = 10  # passages retrieved by semantic similarity alone (BGE-M3), per query
TOP_K_FINAL = 5  # passages kept after combining semantic + lexical scores (SIMPLE questions)
TOP_K_LISTE_MAX = 12  # maximum number of passages sent to Qwen for a LISTE question
BONUS_PAR_MOT = 0.05  # bonus added per important word from the question found exactly in the passage

# Words too common to be useful for lexical search: ignored when
# extracting the "important words" from the question.
MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "est", "quel", "quelle"}

# Words that signal a question asking for SEVERAL elements (list, steps,
# workstreams, recommendations...) rather than a single precise piece of information.
MOTS_CLES_LISTE = [
    "quels sont",
    "quelles sont",
    "liste",
    "étapes",
    "chantiers",
    "recommandations",
    "éléments",
    "points",
]

NB_REFORMULATIONS = 3  # number of alternative rephrasings generated for a LISTE question
SEUIL_STATUT_COMPLETE = 3  # number of validated claims from which a list is considered "complete"

REPONSE_NON_TROUVEE = "Information non trouvée dans le document."

MAX_NEW_TOKENS = 400  # leaves room for list-type answers (several claims)
CITATION_MAX_CARACTERES = 200  # maximum requested length for a citation

# Key terms we want to locate in the document independently of the
# questions asked (used to check that PDF splitting/extraction didn't
# "lose" an important piece of information).
TERMES_DIAGNOSTIC = ["vLLM", "moteur central", "Concevoir la plateforme"]

# System message: forces Qwen to rely only on the supplied passages
# (identified P1 to P5), and to split its answer into claims, each backed
# by precise proof (passage + page + citation).
SYSTEM_PROMPT = (
    "Tu es un assistant documentaire. Tu réponds toujours en français. Tu dois "
    "répondre UNIQUEMENT à partir des passages fournis dans le message de "
    "l'utilisateur, identifiés par P1, P2, P3, P4, P5. Ne complète jamais avec "
    "tes connaissances générales, même si tu penses connaître la réponse.\n\n"
    "Si les passages ne contiennent pas clairement la réponse, réponds "
    f'uniquement avec la phrase exacte : "{REPONSE_NON_TROUVEE}" (rien d\'autre).\n\n'
    "Sinon, découpe ta réponse en affirmations séparées : une seule affirmation "
    "pour une réponse simple, ou une affirmation distincte par élément si la "
    "réponse est une liste (6 éléments maximum). Pour CHAQUE affirmation, utilise "
    "STRICTEMENT ce format, sur 4 lignes :\n"
    "AFFIRMATION: <une seule affirmation, phrase complète>\n"
    "PASSAGE: <identifiant, ex. P2>\n"
    "PAGE: <numéro de page>\n"
    f'CITATION: "<citation copiée EXACTEMENT depuis ce passage, {CITATION_MAX_CARACTERES} '
    'caractères maximum>"\n\n'
    "Répète ce bloc de 4 lignes pour chaque affirmation. Termine toujours tes phrases "
    "(n'écris jamais une phrase coupée)."
)

# The verifier NEVER sees the document: only the question, the claim, and
# the citation supposed to prove it. This is an independent second
# opinion, not a mere re-reading of Qwen's first reasoning.
VERIFICATEUR_SYSTEM_PROMPT = (
    "Tu es un vérificateur strict. Tu reçois une question, une affirmation et une "
    "citation censée prouver cette affirmation. Réponds par un seul mot : "
    "SUPPORTED si la citation prouve clairement l'affirmation pour cette question, "
    "ou NOT_SUPPORTED si ce n'est pas le cas ou si c'est ambigu. N'écris rien d'autre."
)

# For LISTE questions: no answer is requested at this stage, only useful
# rephrasings to retrieve more relevant passages (a list or table is
# often spread across several phrasings).
REFORMULATION_SYSTEM_PROMPT = (
    "Tu aides à améliorer une recherche documentaire. On te donne une question. "
    "Propose 3 reformulations différentes de cette question, avec d'autres mots, "
    "pour retrouver davantage de passages pertinents dans un document. Ne réponds "
    "PAS à la question : donne uniquement les 3 reformulations, une par ligne, "
    "sans numérotation ni commentaire."
)

# Questions automatically asked at the end of the script.
# The last one ("CFO") deliberately tests a piece of information that
# probably doesn't exist in this technical document.
QUESTIONS = [
    "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
    "Quel runtime LLM principal est recommandé ?",
    "Quels sont les grands chantiers couverts par cette Epic ?",
    "Quel est le nom du directeur financier d'AFTECH ?",
]


def decouper_texte(texte, taille=TAILLE_PASSAGE, chevauchement=CHEVAUCHEMENT):
    """Splits a long text into fixed-size passages, with overlap.

    The overlap prevents an important sentence from being cut in two and
    losing all its meaning if it happens to fall right at the boundary
    between two passages.
    """
    passages = []
    debut = 0
    while debut < len(texte):
        fin = debut + taille
        passage = texte[debut:fin].strip()
        if passage:
            passages.append(passage)
        debut += taille - chevauchement
    return passages


def charger_passages_pdf():
    """Reads the PDF page by page and splits it into passages.

    For each passage, keeps the PDF's name and the real page number
    (starting at 1): this is what will later let us say precisely "the
    answer comes from page X".
    """
    nom_pdf = os.path.basename(PDF_PATH)
    lecteur = PdfReader(PDF_PATH)

    passages = []  # text of each passage
    pages = []  # matching page number (same index as "passages")

    for indice_page, page in enumerate(lecteur.pages):
        numero_page = indice_page + 1  # human page numbers start at 1, not 0
        texte_page = page.extract_text() or ""

        for morceau in decouper_texte(texte_page):
            passages.append(morceau)
            pages.append(numero_page)

    return nom_pdf, passages, pages


def extraire_mots_importants(question):
    """Removes overly common words from a question, keeping only the meaning-carrying words."""
    mots = re.findall(r"\w+", question.lower(), re.UNICODE)
    return [mot for mot in mots if mot not in MOTS_VIDES and len(mot) > 1]


def calculer_bonus_lexical(mots_importants, texte_passage):
    """Adds a bonus for each important word from the question found EXACTLY in the passage.

    This bonus complements the semantic score (BGE-M3): meaning can be
    close without the exact word being present, and conversely a rare
    exact word (e.g. a proper noun or a technical term like "vLLM") is a
    strong signal that the semantic score alone might underrate.
    """
    texte_lower = texte_passage.lower()
    nb_trouves = sum(
        1 for mot in mots_importants if re.search(rf"\b{re.escape(mot)}\b", texte_lower)
    )
    return nb_trouves * BONUS_PAR_MOT


def classifier_question(question):
    """Distinguishes a SIMPLE question (one precise piece of information)
    from a LISTE question (several elements, steps, workstreams or
    recommendations expected).

    Simple keyword-based rule: no need to call Qwen for this, the
    question's phrasing is enough in the vast majority of cases.
    """
    question_normalisee = question.lower()
    if any(mot_cle in question_normalisee for mot_cle in MOTS_CLES_LISTE):
        return "LISTE"
    return "SIMPLE"


def rechercher_candidats(question, embedder, embeddings_passages, passages, top_k=TOP_K_INITIAL):
    """Searches, for ONE question phrasing, the semantically closest
    passages (BGE-M3), then adds each one's lexical bonus.

    Returns a list of candidates identified by their index in the global
    "passages" list (no "P1, P2..." ids yet at this stage: those come
    after merging several phrasings, for a LISTE question).
    """
    embedding_question = embedder.encode(question, convert_to_tensor=True)
    scores_semantiques = util.cos_sim(embedding_question, embeddings_passages)[0]

    nb = min(top_k, len(passages))
    indices = torch.topk(scores_semantiques, k=nb).indices.tolist()
    mots_importants = extraire_mots_importants(question)

    candidats = []
    for indice in indices:
        score_semantique = float(scores_semantiques[indice])
        bonus_lexical = calculer_bonus_lexical(mots_importants, passages[indice])
        candidats.append(
            {
                "indice": indice,
                "score_semantique": score_semantique,
                "bonus_lexical": bonus_lexical,
                "score_final": score_semantique + bonus_lexical,
            }
        )
    return candidats


def generer_reformulations(question, tokenizer, model):
    """Asks Qwen for 3 rephrasings of the question, ONLY to widen the
    search (Qwen doesn't answer the question at this stage)."""
    messages = [
        {"role": "system", "content": REFORMULATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question : {question}"},
    ]
    texte_brut = generer_texte(messages, tokenizer, model, max_new_tokens=150)

    reformulations = []
    for ligne in texte_brut.splitlines():
        ligne = re.sub(r"^[\s\-\*\d\.\)]+", "", ligne).strip()
        if ligne:
            reformulations.append(ligne)

    return reformulations[:NB_REFORMULATIONS]


def _passage_depuis_candidat(rang, indice, candidat, passages, pages, nom_pdf):
    """Builds the final dict for a passage (with its Pn id) from a
    candidate identified by its index in the global passages list."""
    return {
        "id": f"P{rang + 1}",
        "texte": passages[indice],
        "page": pages[indice],
        "pdf": nom_pdf,
        "score_semantique": candidat["score_semantique"],
        "bonus_lexical": candidat["bonus_lexical"],
        "score_final": candidat["score_final"],
    }


def recuperer_passages(question, embedder, embeddings_passages, passages, pages, nom_pdf):
    """Finds the TOP_K_FINAL best passages for a SIMPLE question: a single
    search, sorted on the combined semantic score + lexical bonus."""
    candidats = rechercher_candidats(question, embedder, embeddings_passages, passages)
    candidats.sort(key=lambda c: c["score_final"], reverse=True)
    meilleurs = candidats[:TOP_K_FINAL]

    return [
        _passage_depuis_candidat(rang, c["indice"], c, passages, pages, nom_pdf)
        for rang, c in enumerate(meilleurs)
    ]


def rechercher_passages_liste(
    question, reformulations, embedder, embeddings_passages, passages, pages, nom_pdf
):
    """Widened search for a LISTE question:

    1) queries the original question + its rephrasings;
    2) merges the results, removing duplicates (keeps the best score seen
       for each passage);
    3) adds the previous and next passage of each kept passage, only if
       they're on the same page (so as not to cut a table or list that
       spans two passages);
    4) caps the whole thing at TOP_K_LISTE_MAX passages before sending
       them to Qwen.
    """
    # Steps 1 + 2: merge and dedupe across all phrasings
    meilleur_candidat_par_indice = {}
    for formulation in [question] + reformulations:
        for candidat in rechercher_candidats(formulation, embedder, embeddings_passages, passages):
            indice = candidat["indice"]
            existant = meilleur_candidat_par_indice.get(indice)
            if existant is None or candidat["score_final"] > existant["score_final"]:
                meilleur_candidat_par_indice[indice] = candidat

    # Step 3: neighborhood expansion (identical previous/next page)
    candidats_etendus = dict(meilleur_candidat_par_indice)
    for indice, candidat in list(meilleur_candidat_par_indice.items()):
        for indice_voisin in (indice - 1, indice + 1):
            deja_present = indice_voisin in candidats_etendus
            dans_les_limites = 0 <= indice_voisin < len(passages)
            if not dans_les_limites or deja_present:
                continue
            if pages[indice_voisin] != pages[indice]:
                continue
            # The neighbor is added for context (to reconstruct a
            # table/list that got split), not because it was judged
            # relevant itself: it inherits a score slightly lower than
            # its originating passage.
            candidats_etendus[indice_voisin] = {
                "indice": indice_voisin,
                "score_semantique": 0.0,
                "bonus_lexical": 0.0,
                "score_final": candidat["score_final"] * 0.99,
            }

    # Step 4: keep the TOP_K_LISTE_MAX best scores...
    candidats_tries = sorted(candidats_etendus.values(), key=lambda c: c["score_final"], reverse=True)
    meilleurs = candidats_tries[:TOP_K_LISTE_MAX]
    # ...then put them back in the document's reading order: easier for
    # Qwen to reconstruct a table/list in the right order.
    meilleurs.sort(key=lambda c: c["indice"])

    return [
        _passage_depuis_candidat(rang, c["indice"], c, passages, pages, nom_pdf)
        for rang, c in enumerate(meilleurs)
    ]


def construire_prompt(question, passages):
    """Builds the context (identified passages + page number) sent to Qwen."""
    # NOTE (presentation build): text sent to the LLM, left untranslated
    # on purpose — see this module's docstring.
    contexte = "\n\n".join(f"[{p['id']} | page {p['page']}] {p['texte']}" for p in passages)
    return f"Passages du document :\n{contexte}\n\nQuestion : {question}"


# Invisible Unicode characters to strip (invisible hyphen, zero-width
# spaces and joiners): PDF layout often adds these without them being
# visible, which can break an otherwise correct text comparison.
CARACTERES_INVISIBLES = "­​‌‍⁠﻿"


def normalize_text(texte):
    """Normalizes a text to reliably compare a citation and a passage.

    Steps, in order:
    1) unicodedata.normalize("NFKC", ...): unifies Unicode variants of
       the same character (e.g. ligature "ﬁ" -> "fi").
    2) non-breaking spaces -> regular space.
    3) invisible hyphens / zero-width characters -> removed.
    4) literal "\\n" sequence (backslash + n, not a real line break,
       which can appear if Qwen writes the escape out in full)
       -> replaced with a space.
    5) real line breaks / tabs -> space.
    6) consecutive spaces collapsed to one, leading/trailing spaces trimmed.
    7) lowercase (for comparison only, not for display).
    """
    texte = unicodedata.normalize("NFKC", texte)
    texte = texte.replace(" ", " ").replace(" ", " ")

    for caractere in CARACTERES_INVISIBLES:
        texte = texte.replace(caractere, "")

    texte = texte.replace("\\n", " ")
    texte = texte.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texte = " ".join(texte.split())

    return texte.lower()


def afficher_diagnostic_termes(passages, pages):
    """Prints, independently of the questions asked, where key terms are located.

    Used to check that splitting into passages didn't "cut" or lose an
    important piece of information somewhere in the document.
    """
    print("=== Diagnostic: searching for key terms in the document ===")
    for terme in TERMES_DIAGNOSTIC:
        terme_normalise = normalize_text(terme)
        print(f'Term searched: "{terme}"')
        trouve = False
        for indice, texte in enumerate(passages):
            if terme_normalise in normalize_text(texte):
                trouve = True
                extrait = texte[:120].replace("\n", " ")
                print(f"  - page {pages[indice]}: {extrait}...")
        if not trouve:
            print("  (no occurrence found)")
    print()


# A claim block looks like:
# AFFIRMATION: <text>
# PASSAGE: P2
# PAGE: 6
# CITATION: "text copied from the passage"
PATTERN_AFFIRMATION = re.compile(
    r"AFFIRMATION\s*:\s*(?P<affirmation>.+?)\s*"
    r"PASSAGE\s*:\s*(?P<passage_id>\S+)\s*"
    r"PAGE\s*:\s*(?P<page>\d+)\s*"
    r'CITATION\s*:\s*"(?P<citation>.+?)"',
    re.IGNORECASE | re.DOTALL,
)


def parser_affirmations(texte_brut):
    """Extracts the list of claims (with their proof) from the structured format.

    Returns a list of dicts {"affirmation", "passage_id", "page", "citation"}.
    An empty list means Qwen provided no structured claim (typically
    because it answered directly with the "not found" sentence).
    """
    return [
        {
            "affirmation": m.group("affirmation").strip(),
            "passage_id": m.group("passage_id").strip().upper(),
            "page": int(m.group("page")),
            "citation": m.group("citation").strip(),
        }
        for m in PATTERN_AFFIRMATION.finditer(texte_brut)
    ]


def citation_est_presente(citation, passage):
    """First check: does the citation exist word-for-word in the FULL PASSAGE?

    Important: compare against the entire passage actually sent to Qwen,
    never a truncated excerpt — otherwise a correct citation that's
    merely absent from the excerpt would be wrongly rejected.
    """
    if not passage or not citation.strip():
        return False
    return normalize_text(citation) in normalize_text(passage["texte"])


def generer_texte(messages, tokenizer, model, max_new_tokens):
    """Sends messages to Qwen and returns the generated text (shared
    utility for both answer generation and verification)."""
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)

    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
    )

    generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True)


def verifier_affirmation(question, affirmation, citation, tokenizer, model):
    """Second check, independent of the first: Qwen is asked again,
    WITHOUT being given the document, whether the citation really proves the claim.

    The verifier only receives the question, the claim and the citation —
    never the full passage nor the other passages — so it judges only
    whether the offered proof holds up, without being able to "find" the
    answer elsewhere in the document.
    """
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
    verdict_brut = generer_texte(messages, tokenizer, model, max_new_tokens=10).strip().upper()

    # Test NOT_SUPPORTED first: the substring "SUPPORTED" is also present
    # in "NOT_SUPPORTED", so the test order matters.
    if "NOT_SUPPORTED" in verdict_brut:
        return False
    return "SUPPORTED" in verdict_brut


def main():
    # --- Step 1: read and split the PDF ("Retrieval" part) ---
    print(f"Reading the PDF: {PDF_PATH}")
    nom_pdf, passages, pages = charger_passages_pdf()
    print(f"{len(passages)} passages extracted across {len(set(pages))} pages.\n")

    afficher_diagnostic_termes(passages, pages)

    print(f"Loading embedding model {EMBEDDING_MODEL_NAME} on CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Computing embeddings for all passages...\n")
    embeddings_passages = embedder.encode(passages, convert_to_tensor=True)

    # --- Step 2: prepare the generation model ("Generation" part) ---
    if not torch.cuda.is_available():
        raise RuntimeError("No GPU detected. This script must run on a Colab session with a GPU.")

    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU detected: {gpu_name}")

    # The Tesla T4 doesn't handle bfloat16 correctly: force float16 in this specific case
    if "T4" in gpu_name:
        compute_dtype = torch.float16
    elif torch.cuda.is_bf16_supported():
        compute_dtype = torch.bfloat16
    else:
        compute_dtype = torch.float16
    print(f"Compute dtype used: {compute_dtype}")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading model {LLM_MODEL_NAME} in 4-bit...\n")
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL_NAME,
        quantization_config=quant_config,
        device_map="auto",
    )

    # --- Step 3: answer each question ---
    resultats_tests = []

    for question in QUESTIONS:
        print("=" * 70)
        print(f"Question: {question}")

        type_question = classifier_question(question)
        print(f"Question type: {type_question}\n")

        if type_question == "LISTE":
            reformulations = generer_reformulations(question, tokenizer, model)
            print("Rephrasings used to widen the search:")
            for reformulation in reformulations:
                print(f"  - {reformulation}")
            print()
            passages_trouves = rechercher_passages_liste(
                question, reformulations, embedder, embeddings_passages, passages, pages, nom_pdf
            )
        else:
            reformulations = []
            passages_trouves = recuperer_passages(
                question, embedder, embeddings_passages, passages, pages, nom_pdf
            )

        pages_utilisees = sorted({p["page"] for p in passages_trouves})

        # Dictionary to look up the FULL passage from its id (P1, P2, ...):
        # this full text is what's used to validate citations, not the
        # short excerpt displayed below.
        passages_par_id = {p["id"]: p for p in passages_trouves}

        print(f"PDF: {nom_pdf}")
        print(f"Pages used: {pages_utilisees}")
        print("Passages found (semantic score, lexical bonus, final score):")
        for p in passages_trouves:
            extrait = p["texte"][:120].replace("\n", " ")
            print(
                f"  - {p['id']} | page {p['page']} | "
                f"semantic={p['score_semantique']:.3f} | "
                f"bonus={p['bonus_lexical']:.3f} | "
                f"final={p['score_final']:.3f}: {extrait}..."
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": construire_prompt(question, passages_trouves)},
        ]
        reponse_brute = generer_texte(messages, tokenizer, model, MAX_NEW_TOKENS)

        affirmations = parser_affirmations(reponse_brute)

        # For each claim: two independent checks.
        for aff in affirmations:
            passage = passages_par_id.get(aff["passage_id"])
            aff["citation_presente"] = citation_est_presente(aff["citation"], passage)

            # No point calling Qwen a second time if the citation doesn't
            # even exist in the passage: the claim is rejected either way
            # (both conditions are mandatory).
            if aff["citation_presente"]:
                aff["preuve_supported"] = verifier_affirmation(
                    question, aff["affirmation"], aff["citation"], tokenizer, model
                )
            else:
                aff["preuve_supported"] = False

            aff["affirmation_validee"] = aff["citation_presente"] and aff["preuve_supported"]

        affirmations_gardees = [a for a in affirmations if a["affirmation_validee"]]

        if not affirmations_gardees:
            # No claim survived both checks: keep nothing rather than risk
            # displaying false information.
            reponse_finale = REPONSE_NON_TROUVEE
        elif len(affirmations_gardees) == 1:
            reponse_finale = affirmations_gardees[0]["affirmation"]
        else:
            reponse_finale = "\n".join(f"- {a['affirmation']}" for a in affirmations_gardees)

        # Final status: purely informative for a SIMPLE question (only one
        # claim possible), but useful for a LISTE question to know whether
        # the reconstructed list is likely complete.
        nb_validees = len(affirmations_gardees)
        if nb_validees == 0:
            statut = "NOT_FOUND"
        elif type_question == "LISTE" and nb_validees < SEUIL_STATUT_COMPLETE:
            statut = "PARTIAL"
        else:
            statut = "COMPLETE"

        print(f"\nAnswer: {reponse_finale}")
        print(f"Status: {statut}")
        if statut == "PARTIAL":
            print("Partial answer: some elements may be missing.")
        print("Claims:")
        if affirmations:
            for a in affirmations:
                statut_affirmation = "validated" if a["affirmation_validee"] else "DROPPED"
                print(
                    f"  - [{statut_affirmation}] {a['affirmation']!r} "
                    f"({a['passage_id']}, page {a['page']}) "
                    f"citation_presente={a['citation_presente']} "
                    f"preuve_supported={a['preuve_supported']}"
                )
        else:
            print("  (none)")
        print()

        resultats_tests.append(
            {
                "question": question,
                "type_question": type_question,
                "statut": statut,
                "reponse": reponse_finale,
                "pdf": nom_pdf,
                "pages": pages_utilisees,
                "reformulations": reformulations,
                "affirmations": [
                    {
                        "affirmation": a["affirmation"],
                        "passage_id": a["passage_id"],
                        "page": a["page"],
                        "citation": a["citation"],
                        "citation_presente": a["citation_presente"],
                        "preuve_supported": a["preuve_supported"],
                        "affirmation_validee": a["affirmation_validee"],
                    }
                    for a in affirmations
                ],
            }
        )

    # --- Step 4: save the results ---
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(resultats_tests, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
