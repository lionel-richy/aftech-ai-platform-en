import pytest
from pdf_helpers import pdf_chiffre, pdf_valide

from app.document_pipeline import (
    DocumentRegistry,
    EnregistrementDocument,
    FichierInvalide,
    calculer_sha256,
    nom_affichage_securise,
    valider_fichier_pdf,
)


class TestValidationPdf:
    def test_pdf_valide_est_accepte(self):
        valider_fichier_pdf(pdf_valide(), "rapport.pdf")  # raises nothing

    def test_mauvais_type_refuse(self):
        with pytest.raises(FichierInvalide, match=r"\.pdf"):
            valider_fichier_pdf(b"this is not a pdf", "fichier.txt")

    def test_extension_pdf_mais_contenu_non_pdf_refuse(self):
        # Requirement: REAL signature check, not just the extension.
        with pytest.raises(FichierInvalide, match="signature"):
            valider_fichier_pdf(b"<html>fake pdf</html>", "faux.pdf")

    def test_pdf_vide_refuse(self):
        with pytest.raises(FichierInvalide, match="empty"):
            valider_fichier_pdf(b"", "vide.pdf")

    def test_fichier_trop_volumineux_refuse(self):
        contenu = pdf_valide() + b"0" * (10 * 1024 * 1024)
        with pytest.raises(FichierInvalide, match="large"):
            valider_fichier_pdf(contenu, "gros.pdf", taille_max_octets=5 * 1024 * 1024)

    def test_pdf_chiffre_refuse(self):
        with pytest.raises(FichierInvalide, match="Encrypted"):
            valider_fichier_pdf(pdf_chiffre(), "protege.pdf")

    def test_pdf_corrompu_refuse(self):
        contenu_corrompu = pdf_valide()[:200]  # truncated: signature OK, structure broken
        with pytest.raises(FichierInvalide, match="corrupted"):
            valider_fichier_pdf(contenu_corrompu, "corrompu.pdf")


class TestNomAffichageSecurise:
    def test_nom_normal_inchange(self):
        assert nom_affichage_securise("rapport_2026.pdf") == "rapport_2026.pdf"

    @pytest.mark.parametrize(
        "nom_malveillant",
        [
            "../../../etc/passwd.pdf",
            "..\\..\\windows\\system32\\config.pdf",
            "/etc/passwd.pdf",
            "a/b/c.pdf",
        ],
    )
    def test_nom_malveillant_ne_contient_plus_de_separateur_de_chemin(self, nom_malveillant):
        resultat = nom_affichage_securise(nom_malveillant)
        assert "/" not in resultat
        assert "\\" not in resultat
        assert ".." not in resultat

    def test_nom_avec_caracteres_de_controle_nettoye(self):
        resultat = nom_affichage_securise("rapport\x00\n\t.pdf")
        assert "\x00" not in resultat
        assert "\n" not in resultat


class TestDocumentRegistry:
    def test_ajouter_et_lister(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        enregistrement = EnregistrementDocument(
            id="abc123", nom_original="x.pdf", nom_stocke="abc123.pdf", taille_octets=10, hash_sha256="h1"
        )
        registry.ajouter(enregistrement)

        assert len(registry.lister()) == 1
        assert registry.obtenir("abc123")["nom_original"] == "x.pdf"

    def test_trouve_doublon_par_sha256(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        registry.ajouter(
            EnregistrementDocument(
                id="a", nom_original="x.pdf", nom_stocke="a.pdf", taille_octets=10, hash_sha256="memehash"
            )
        )

        trouve = registry.trouver_par_hash("memehash")
        assert trouve is not None
        assert trouve["id"] == "a"

        assert registry.trouver_par_hash("autrehash") is None

    def test_doublon_en_cours_de_suppression_nest_pas_compte(self, tmp_path):
        registry = DocumentRegistry(str(tmp_path))
        registry.ajouter(
            EnregistrementDocument(
                id="a", nom_original="x.pdf", nom_stocke="a.pdf", taille_octets=10, hash_sha256="h", statut="DELETING"
            )
        )
        assert registry.trouver_par_hash("h") is None

    def test_calculer_sha256_est_deterministe(self):
        assert calculer_sha256(b"contenu") == calculer_sha256(b"contenu")
        assert calculer_sha256(b"contenu") != calculer_sha256(b"autre")
