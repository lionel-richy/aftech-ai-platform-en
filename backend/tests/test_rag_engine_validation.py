"""Regression tests for RagEngine's validation mechanism.

Context: a false NOT_FOUND was observed in production for the question
"Quel document contient des informations relatives à Azure ?" (Which
document contains information about Azure?) — the search did find 8
relevant passages in AZ-900-Master-Cheat-Sheet.pdf, but Qwen answered
directly with "Information not found in the documents." without even
attempting a claim. Cause: the prompt didn't cover "meta" questions
(which document talks about X?), leading Qwen to look for a sentence
that literally says "this document talks about X" instead of recognizing
that a passage on the topic is enough. Fixed in SYSTEM_PROMPT.

These tests use a REAL RagEngine (so its REAL validation logic), but
with a fake embedder/index (no real FAISS/BGE-M3 — unnecessary here,
we're not testing search relevance, already verified manually against
the real index) and a simulated `_generer_texte` to precisely control
what "Qwen" answers in each scenario.
"""

import numpy as np
import pytest

from app.rag_engine import REPONSE_NON_TROUVEE, RagEngine


class FakeEmbedder:
    def encode(self, textes, convert_to_numpy=True, normalize_embeddings=True):
        return np.zeros((len(textes), 4), dtype="float32")


class FakeIndex:
    """Simulates FAISS: returns the chunks in the order they were added,
    with plausible decreasing scores. Enough to test validation — the
    search's real relevance has already been verified separately against
    the real index (see this bug's diagnosis)."""

    def __init__(self, nb_chunks):
        self.nb_chunks = nb_chunks

    def search(self, embedding_question, k):
        k = min(k, self.nb_chunks)
        indices = np.arange(k).reshape(1, -1)
        scores = np.linspace(0.9, 0.5, k).reshape(1, -1).astype("float32")
        return scores, indices


def construire_engine(chunks: list[dict]) -> RagEngine:
    engine = RagEngine(index_dir="/non-utilise")
    engine.embedder = FakeEmbedder()
    engine.index = FakeIndex(len(chunks))
    engine.chunks = chunks
    engine.manifest = {"pdf": sorted({c["source"] for c in chunks})}
    engine.ready = True
    engine.tokenizer = object()  # never used: _generer_texte is simulated below
    engine.model = object()
    return engine


def simuler_generation(textes_bruts: list[str]):
    """Replaces RagEngine._generer_texte: returns each text from the list
    in turn (1st call = main generation, next ones = verifier), with
    arbitrary token counts (not tested here)."""
    iterateur = iter(textes_bruts)

    def _mock(messages, max_new_tokens):
        return next(iterateur), 500, 50

    return _mock


def bloc_affirmation(affirmation: str, passage_id: str, page: int, citation: str) -> str:
    return f'AFFIRMATION: {affirmation}\nPASSAGE: {passage_id}\nPAGE: {page}\nCITATION: "{citation}"'


# --- Content fixtures, inspired by the real indexed documents ---

CHUNK_AZURE = {
    "texte": (
        "Azure offers a wide range of resource types, including compute, storage, "
        "networking, and databases."
    ),
    "source": "AZ-900-Master-Cheat-Sheet.pdf",
    "page": 12,
}
CHUNK_VLLM = {
    "texte": "Le runtime LLM principal recommandé est vLLM, pour sa gestion efficace du batching.",
    "source": "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf",
    "page": 6,
}
CHUNK_ACCOMPAGNEMENT = {
    "texte": "Ce document décrit la procédure d'accompagnement des salariés en reconversion professionnelle.",
    "source": "Accompagnement2004.pdf",
    "page": 1,
}


class TestReponsesAcceptees:
    """Precisely reproduces the reported bug, and two neighboring cases —
    checks that they're now accepted (no more false NOT_FOUND)."""

    def test_question_azure_est_acceptee(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure propose des types de ressources variés (calcul, stockage, réseau, bases de données).",
                        "P1",
                        12,
                        CHUNK_AZURE["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Quel document contient des informations relatives à Azure ?")

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert resultat["answer"] != REPONSE_NON_TROUVEE
        assert "AZ-900-Master-Cheat-Sheet.pdf" in resultat["answer"]
        assert len(resultat["validated_claims"]) == 1

    def test_document_vllm_est_accepte(self, monkeypatch):
        engine = construire_engine([CHUNK_VLLM])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Le runtime LLM principal recommandé est vLLM.",
                        "P1",
                        6,
                        CHUNK_VLLM["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Quel document parle de vLLM ?")

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf" in resultat["answer"]

    def test_resume_accompagnement_est_utile(self, monkeypatch):
        engine = construire_engine([CHUNK_ACCOMPAGNEMENT])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Le document décrit la procédure d'accompagnement des salariés en reconversion professionnelle.",
                        "P1",
                        1,
                        CHUNK_ACCOMPAGNEMENT["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask("Résume le sujet principal du document Accompagnement2004.pdf.")

        assert resultat["status"] != "NOT_FOUND"
        assert resultat["answer"] != REPONSE_NON_TROUVEE


class TestAbsenceReelleResteNotFound:
    """The anti-hallucination mechanism must keep rejecting information
    that's genuinely absent."""

    def test_directeur_financier_absent_donne_not_found(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE, CHUNK_VLLM, CHUNK_ACCOMPAGNEMENT])
        # No passage contains this information: Qwen answers directly
        # with the sentence, with no AFFIRMATION block (intended behavior).
        monkeypatch.setattr(engine, "_generer_texte", simuler_generation([REPONSE_NON_TROUVEE]))

        resultat = engine.ask("Quel est le nom du directeur financier d'AFTECH ?")

        assert resultat["status"] == "NOT_FOUND"
        assert resultat["answer"] == REPONSE_NON_TROUVEE
        assert resultat["validated_claims"] == []


class TestRejetsDeSecurite:
    """The anti-hallucination mechanism must keep rejecting unproven
    claims — the prompt fix must not weaken anything here."""

    def test_citation_inventee_est_rejetee(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure a été lancé en février 2008.",
                        "P1",
                        12,
                        # Plausible but FABRICATED citation: absent from the passage's real text.
                        "Azure a été lancé officiellement en février 2008 par Microsoft.",
                    ),
                    # No second element: the verifier must NEVER be called
                    # here (citation_presente fails before that). If it
                    # were, this test would fail with StopIteration.
                ]
            ),
        )

        resultat = engine.ask("Quand Azure a-t-il été lancé ?")

        assert resultat["status"] == "NOT_FOUND"
        assert resultat["answer"] == REPONSE_NON_TROUVEE

    def test_citation_reelle_mais_mal_attribuee_est_rejetee(self, monkeypatch):
        # The citation exists word-for-word in the corpus, but Qwen
        # attributes it to the wrong passage (P2 = vLLM, while the text
        # actually comes from elsewhere): our ground truth (not the LLM)
        # must detect the inconsistency.
        engine = construire_engine([CHUNK_AZURE, CHUNK_VLLM])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure propose du stockage.",
                        "P2",  # vLLM passage, not Azure
                        6,
                        CHUNK_AZURE["texte"],  # real citation, but taken from the wrong passage
                    ),
                ]
            ),
        )

        resultat = engine.ask("Que propose Azure comme stockage ?")

        assert resultat["status"] == "NOT_FOUND"


class TestCitationTronqueeParMaxNewTokens:
    """Real bug diagnosed in production (French question about the EU AI
    Act, logs "[rag_engine] no AFFIRMATION parsed"): Qwen sometimes adds
    an introductory paragraph before the structured block, which could
    exhaust MAX_NEW_TOKENS before CITATION's closing quote — the whole
    block then became unreadable by the regex, despite a genuine attempt
    and a faithful citation. Fixed by also accepting a citation ending at
    the end of the generated text (see PATTERN_AFFIRMATION)."""

    def test_citation_tronquee_sans_guillemet_fermante_est_quand_meme_acceptee(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        citation_tronquee = CHUNK_AZURE["texte"][:40]  # faithful prefix, no closing quote
        texte_genere_tronque = (
            "Azure est une plateforme complète.\n\n"  # stray preamble, as seen in production
            "AFFIRMATION: Azure propose des types de ressources variés.\n"
            "PASSAGE: P1\n"
            "PAGE: 12\n"
            f'CITATION: "{citation_tronquee}'  # cut off here, NO closing quote
        )
        monkeypatch.setattr(engine, "_generer_texte", simuler_generation([texte_genere_tronque, "SUPPORTED"]))

        resultat = engine.ask("Quel document contient des informations relatives à Azure ?")

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert len(resultat["validated_claims"]) == 1
        assert resultat["validated_claims"][0]["citation_presente"] is True

    def test_citation_tronquee_qui_ne_correspond_a_rien_reste_rejetee(self, monkeypatch):
        """The safety net must never fabricate a validation: a truncated
        citation that is NOT a real prefix of the passage stays rejected,
        exactly as before this fix."""
        engine = construire_engine([CHUNK_AZURE])
        texte_genere = (
            "AFFIRMATION: Azure propose des types de ressources variés.\n"
            "PASSAGE: P1\n"
            "PAGE: 12\n"
            'CITATION: "ceci est une citation inventée, jamais dans le passage'
        )
        monkeypatch.setattr(engine, "_generer_texte", simuler_generation([texte_genere]))

        resultat = engine.ask("Quel document contient des informations relatives à Azure ?")

        assert resultat["status"] == "NOT_FOUND"
