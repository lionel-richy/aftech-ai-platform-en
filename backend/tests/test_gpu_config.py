"""Modal GPU selection rule (backend/app/gpu_config.py) — no dependency
on `modal`, so testable even without that package installed.

The real integration (this module loaded exactly as `modal deploy` does,
from backend/ as cwd) was verified manually with
`modal.cli.import_refs.import_file_or_module`: successful import with
MODAL_GPU_TYPE unset (-> L4) and explicit rejection with MODAL_GPU_TYPE=A100.
"""

import pytest

from app.gpu_config import GPU_TYPE_DEFAUT, GPU_TYPES_AUTORISES, resoudre_gpu_type


def test_defaut_est_l4():
    assert GPU_TYPE_DEFAUT == "L4"
    assert resoudre_gpu_type(None) == "L4"


def test_t4_autorise_profil_economique():
    assert resoudre_gpu_type("T4") == "T4"


def test_l4_autorise():
    assert resoudre_gpu_type("L4") == "L4"


def test_a100_interdit():
    with pytest.raises(ValueError, match="A100"):
        resoudre_gpu_type("A100")


@pytest.mark.parametrize("valeur", ["H100", "G4", "a4000", "", "t4"])
def test_valeurs_inconnues_interdites(valeur):
    # "t4" (lowercase): case is NOT silently tolerated — better to fail
    # clearly than accept a typo that would deploy on a different GPU
    # than intended.
    with pytest.raises(ValueError):
        resoudre_gpu_type(valeur)


def test_espaces_autour_de_la_valeur_sont_tolere():
    # Surrounding whitespace (e.g. a badly copy-pasted environment
    # variable) is stripped before comparison — but not case (see test
    # above).
    assert resoudre_gpu_type(" T4 ") == "T4"


def test_liste_autorisee_ne_contient_pas_a100():
    assert "A100" not in GPU_TYPES_AUTORISES
    assert set(GPU_TYPES_AUTORISES) == {"T4", "L4"}
