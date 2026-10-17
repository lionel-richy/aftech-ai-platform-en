"""Tests of RagEngine's trilingual contract (response_language).

Requirements covered here:
- the backend answers in response_language EVEN when the source document
  is in a different language (French question on an English document;
  German question on an English document);
- the exact citation (validated_claims[].citation) and the file name
  ALWAYS stay in their original language, never translated;
- an unsupported language is rejected by the engine.

Same test doubles as test_rag_engine_validation.py (pure-numpy
FakeEmbedder/FakeIndex, simulated _generer_texte): search relevance
isn't re-tested here, it's already covered elsewhere.
"""

import pytest

from app.rag_engine import REPONSE_NON_TROUVEE_PAR_LANGUE
from test_rag_engine_validation import (
    CHUNK_AZURE,
    bloc_affirmation,
    construire_engine,
    simuler_generation,
)


class TestReponseDansLaLangueDemandee:
    def test_question_francaise_sur_document_anglais(self, monkeypatch):
        # CHUNK_AZURE is an ENGLISH passage. The question is in French and
        # response_language="fr" (default): the generated claim must be
        # in French, but the CITATION stays the exact English text.
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

        resultat = engine.ask(
            "Quel document contient des informations relatives à Azure ?",
            response_language="fr",
        )

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Azure propose des types de ressources variés" in resultat["answer"]
        assert "[source :" in resultat["answer"]
        claim = resultat["validated_claims"][0]
        # The citation stays the original ENGLISH sentence, verbatim.
        assert claim["citation"] == CHUNK_AZURE["texte"]

    def test_question_allemande_sur_document_anglais(self, monkeypatch):
        engine = construire_engine([CHUNK_AZURE])
        monkeypatch.setattr(
            engine,
            "_generer_texte",
            simuler_generation(
                [
                    bloc_affirmation(
                        "Azure bietet eine Vielzahl von Ressourcentypen (Compute, Speicher, Netzwerk, Datenbanken) an.",
                        "P1",
                        12,
                        CHUNK_AZURE["texte"],
                    ),
                    "SUPPORTED",
                ]
            ),
        )

        resultat = engine.ask(
            "Welches Dokument enthält Informationen zu Azure?",
            response_language="de",
        )

        assert resultat["status"] in ("COMPLETE", "PARTIAL")
        assert "Azure bietet eine Vielzahl" in resultat["answer"]
        # German source suffix ("Quelle"/"Seite"), never translated into
        # French or English.
        assert "[Quelle:" in resultat["answer"]
        assert "Seite 12" in resultat["answer"]
        claim = resultat["validated_claims"][0]
        # The citation stays the original ENGLISH sentence, verbatim —
        # never translated into German.
        assert claim["citation"] == CHUNK_AZURE["texte"]

    def test_not_found_est_dans_la_langue_demandee(self, monkeypatch):
        for langue, phrase_attendue in REPONSE_NON_TROUVEE_PAR_LANGUE.items():
            engine = construire_engine([CHUNK_AZURE])
            monkeypatch.setattr(engine, "_generer_texte", simuler_generation([phrase_attendue]))

            resultat = engine.ask("Quel est le nom du directeur financier d'AFTECH ?", response_language=langue)

            assert resultat["status"] == "NOT_FOUND"
            assert resultat["answer"] == phrase_attendue


class TestLangueInvalide:
    def test_langue_non_supportee_leve_value_error(self):
        engine = construire_engine([CHUNK_AZURE])
        with pytest.raises(ValueError):
            engine.ask("Quand Azure a-t-il été lancé ?", response_language="es")
