"""Tests of the PURE functions in scripts/gpu_benchmark.py (no GPU required)."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from gpu_benchmark import (  # noqa: E402
    DOSSIER_BACKEND_COLAB_DEFAUT,
    agreger,
    determiner_dossier_backend,
    fusionner_config_fichier,
    valider_gpu_attendu,
)


class TestDeterminerDossierBackend:
    """Explicitly covers the reported bug: NameError on __file__ when the
    script is run via `colab exec` (code passed to exec() in an
    already-started Jupyter kernel, where __file__ isn't defined)."""

    def test_sans_fichier_utilise_la_racine_colab(self):
        # Simulates the absence of __file__ (the "colab exec" case): pass nothing.
        resultat = determiner_dossier_backend(None)
        assert resultat == Path(DOSSIER_BACKEND_COLAB_DEFAUT)

    def test_sans_fichier_respecte_une_racine_personnalisee(self):
        resultat = determiner_dossier_backend(None, racine_colab="/tmp/autre")
        assert resultat == Path("/tmp/autre")

    def test_avec_fichier_remonte_au_dossier_backend_du_projet(self):
        # Simulates a normal launch: python scripts/gpu_benchmark.py
        chemin_simule = "/chemin/projet/scripts/gpu_benchmark.py"
        resultat = determiner_dossier_backend(chemin_simule)
        assert resultat == Path("/chemin/projet/backend")


@pytest.mark.parametrize(
    "gpu_attendu,gpu_obtenu,attendu",
    [
        ("T4", "Tesla T4", True),
        ("L4", "NVIDIA L4", True),
        ("A100", "NVIDIA A100-SXM4-40GB", True),
        ("T4", "NVIDIA A100-SXM4-40GB", False),  # requirement: never confuse T4 and A100
        ("A100", "Tesla T4", False),
        ("T4", "", False),
        ("T4", None, False),
    ],
)
def test_valider_gpu_attendu(gpu_attendu, gpu_obtenu, attendu):
    assert valider_gpu_attendu(gpu_attendu, gpu_obtenu) is attendu


def test_agreger_calcule_moyenne_mediane_min_max_ecart_type():
    resultat = agreger([1.0, 2.0, 3.0, 4.0, 5.0])
    assert resultat["moyenne"] == 3.0
    assert resultat["mediane"] == 3.0
    assert resultat["minimum"] == 1.0
    assert resultat["maximum"] == 5.0
    assert resultat["ecart_type"] > 0


def test_agreger_renvoie_none_si_aucune_valeur():
    assert agreger([]) is None
    assert agreger([None, None]) is None


def test_agreger_ecart_type_zero_sur_une_seule_valeur():
    resultat = agreger([42.0])
    assert resultat["ecart_type"] == 0.0


class _ArgsFactices:
    """Minimal object mimicking the namespace returned by argparse."""

    def __init__(self, **kwargs):
        self.gpu_attendu = kwargs.get("gpu_attendu")
        self.output = kwargs.get("output")
        self.index_dir = kwargs.get("index_dir", "data/indexes/aftech_documents")
        self.repetitions = kwargs.get("repetitions", 3)
        self.seed = kwargs.get("seed", 42)
        self.install_timing_file = kwargs.get("install_timing_file")
        self.config = kwargs.get("config", "/chemin/inexistant.json")


class _ParserFactice:
    def error(self, message):
        raise SystemExit(message)


def test_fusionner_config_fichier_ne_touche_rien_si_args_complets():
    args = _ArgsFactices(gpu_attendu="T4", output="sortie.json")
    resultat = fusionner_config_fichier(args, _ParserFactice())
    assert resultat.gpu_attendu == "T4"
    assert resultat.output == "sortie.json"


def test_fusionner_config_fichier_charge_le_fichier_si_args_absents(tmp_path):
    config = tmp_path / "benchmark_config.json"
    config.write_text(json.dumps({"gpu_attendu": "L4", "output": "resultats/L4.json"}), encoding="utf-8")

    args = _ArgsFactices(config=str(config))
    resultat = fusionner_config_fichier(args, _ParserFactice())

    assert resultat.gpu_attendu == "L4"
    assert resultat.output == "resultats/L4.json"


def test_fusionner_config_fichier_echoue_si_rien_de_disponible():
    args = _ArgsFactices(config="/chemin/qui/n_existe_pas.json")
    with pytest.raises(SystemExit):
        fusionner_config_fichier(args, _ParserFactice())
