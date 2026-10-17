"""Tests that scripts/run_gpu_benchmark.sh refuses an unknown GPU BEFORE
any call to Colab (so this test needs neither a Colab account nor network).

NOTE (presentation build): scripts/run_gpu_benchmark.sh has been
translated to English, so the strings asserted on below match its real,
translated output."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_gpu_benchmark.sh"


def _lancer(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_refuse_h100():
    resultat = _lancer("H100")
    assert resultat.returncode == 1
    assert "unknown" in resultat.stdout.lower() or "unknown" in resultat.stderr.lower()


def test_refuse_g4():
    resultat = _lancer("G4")
    assert resultat.returncode == 1


def test_refuse_gpu_vide():
    resultat = _lancer()
    assert resultat.returncode == 1


def test_refuse_valeur_arbitraire():
    resultat = _lancer("pas-un-gpu")
    assert resultat.returncode == 1


def test_accepte_t4_l4_a100_dans_le_filtre_initial():
    """We do NOT go as far as the Colab call here (no network in the
    tests): we only check that T4/L4/A100 pass the first filter, cutting
    execution short right after via a fake 'colab' command absent from
    PATH (so the rest will fail cleanly, but NOT on the name check)."""
    for gpu in ("T4", "L4", "A100"):
        resultat = subprocess.run(
            ["bash", str(SCRIPT), gpu],
            capture_output=True,
            text=True,
            timeout=15,
            env={"PATH": "/usr/bin:/bin"},  # "colab" intentionally unavailable
            input="no\n",  # in case the A100 confirmation prompt appears
        )
        assert "unknown GPU" not in resultat.stdout
