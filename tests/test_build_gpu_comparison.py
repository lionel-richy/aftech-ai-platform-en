"""Tests scripts/build_gpu_comparison.py with fixtures explicitly marked as
test data (tests/fixtures/gpu_benchmark/*.json), never real benchmark data."""

import csv
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gpu_benchmark"
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_gpu_comparison import charger_resultats, construire_csv, construire_recommendation_md  # noqa: E402


def test_charger_resultats_lit_uniquement_les_gpu_presents():
    resultats = charger_resultats(FIXTURES_DIR)
    assert set(resultats.keys()) == {"T4", "L4"}  # A100.json deliberately absent


def test_charger_resultats_sur_dossier_vide_renvoie_dict_vide(tmp_path):
    assert charger_resultats(tmp_path) == {}


def test_construire_csv_a_une_ligne_par_gpu_teste(tmp_path):
    resultats = charger_resultats(FIXTURES_DIR)
    chemin_csv = tmp_path / "comparison.csv"

    lignes = construire_csv(resultats, chemin_csv)

    assert chemin_csv.is_file()
    assert len(lignes) == 2
    gpus = {l["gpu"] for l in lignes}
    assert gpus == {"T4", "L4"}

    with open(chemin_csv, encoding="utf-8") as f:
        lignes_lues = list(csv.DictReader(f))
    assert len(lignes_lues) == 2


def test_construire_csv_sans_aucun_resultat_ecrit_seulement_un_en_tete(tmp_path):
    chemin_csv = tmp_path / "comparison.csv"
    lignes = construire_csv({}, chemin_csv)

    assert lignes == []
    assert chemin_csv.is_file()
    with open(chemin_csv, encoding="utf-8") as f:
        contenu = f.read()
    assert "gpu" in contenu  # header present
    assert len(contenu.strip().splitlines()) == 1  # no made-up data row


def test_recommendation_md_signale_le_gpu_manquant(tmp_path):
    resultats = charger_resultats(FIXTURES_DIR)
    lignes = construire_csv(resultats, tmp_path / "comparison.csv")

    contenu = construire_recommendation_md(resultats, lignes, FIXTURES_DIR)

    assert "A100" in contenu  # mentioned as missing
    assert "not tested" in contenu.lower() or "not run" in contenu.lower()


def test_recommendation_md_sans_aucun_resultat_dit_benchmark_non_execute(tmp_path):
    contenu = construire_recommendation_md({}, [], tmp_path)
    assert "Benchmark not run" in contenu


def test_recommendation_md_ne_jamais_inventer_les_ccu(tmp_path):
    resultats = charger_resultats(FIXTURES_DIR)
    lignes = construire_csv(resultats, tmp_path / "comparison.csv")

    # No <GPU>_usage_avant.txt / _apres.txt file in FIXTURES_DIR: the text
    # must say so explicitly, not make up a compute-units number.
    contenu = construire_recommendation_md(resultats, lignes, FIXTURES_DIR)

    assert "Not measured automatically" in contenu
    assert "we do not make up" in contenu.lower()
