"""Tests the download validation in scripts/run_gpu_benchmark.sh: the
script must NEVER print "Done" if colab exec lied about its success
(a real bug encountered: a Python-side NameError, but colab exec still
returns exit code 0), if the download fails, if the file is empty, or if
its content isn't valid JSON.

NOTE (presentation build): scripts/run_gpu_benchmark.sh has been translated
to English ("ERREUR" is kept deliberately, matching the rest of this
script's style), so the strings asserted on below match its real,
translated output.

These tests need NEITHER a real Colab account NOR the rest of the project:
a fake "colab" executable (placed first in PATH) simulates every
subcommand, and the script runs in an isolated temporary folder.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT_REEL = Path(__file__).resolve().parents[1] / "scripts" / "run_gpu_benchmark.sh"

FAUX_COLAB = r"""#!/bin/bash
# Fake "colab" CLI for the tests: simulates every subcommand used by
# run_gpu_benchmark.sh, with no network access at all.

# Last argument (portable, no need for bash >= 4.3 negative indexing)
for DERNIER_ARG in "$@"; do :; done

case "$*" in
  *"status -s"*)
    echo "not found"
    exit 0
    ;;
  *"sessions"*)
    exit 0
    ;;
  *"usage"*)
    exit 1
    ;;
  *"new -s"*)
    echo "Session READY."
    exit 0
    ;;
  *"install -s"*)
    exit 0
    ;;
  *"upload "*)
    exit 0
    ;;
  *"exec -s"*"-f scripts/gpu_benchmark.py"*)
    # Simulates exactly the reported bug: the remote Python script crashed
    # (NameError), but "colab exec" still returns success.
    exit 0
    ;;
  *"exec -s"*)
    cat >/dev/null  # consume the input (mkdir command sent via a pipe)
    exit 0
    ;;
  *"download -s"*)
    case "$FAKE_DOWNLOAD_MODE" in
      fail)
        exit 1
        ;;
      empty)
        : > "$DERNIER_ARG"
        exit 0
        ;;
      invalid_json)
        echo "ceci n'est pas du JSON" > "$DERNIER_ARG"
        exit 0
        ;;
      *)
        echo '{"configuration": {"gpu_demande": "T4"}}' > "$DERNIER_ARG"
        exit 0
        ;;
    esac
    ;;
  *"stop -s"*)
    echo "stop called" >> "$COLAB_STUB_STOP_LOG"
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""


@pytest.fixture
def environnement_test(tmp_path):
    """Isolated working folder + fake "colab" first in PATH."""
    dossier_bin = tmp_path / "fakebin"
    dossier_bin.mkdir()
    chemin_colab = dossier_bin / "colab"
    chemin_colab.write_text(FAUX_COLAB, encoding="utf-8")
    chemin_colab.chmod(chemin_colab.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    journal_stop = tmp_path / "stop.log"

    environnement = os.environ.copy()
    environnement["PATH"] = f"{dossier_bin}:{environnement['PATH']}"
    environnement["COLAB_STUB_STOP_LOG"] = str(journal_stop)

    return tmp_path, environnement, journal_stop


def lancer_script(tmp_path, environnement, mode_telechargement):
    environnement = {**environnement, "FAKE_DOWNLOAD_MODE": mode_telechargement}
    return subprocess.run(
        ["bash", str(SCRIPT_REEL), "T4"],
        cwd=tmp_path,
        env=environnement,
        capture_output=True,
        text=True,
        timeout=30,
        input="yes\n",  # in case a confirmation is requested
    )


class TestValidationTelechargement:
    def test_succes_affiche_termine_et_fichier_valide(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "success")

        assert resultat.returncode == 0
        assert "Done" in resultat.stdout
        fichier = tmp_path / "results" / "benchmarks" / "gpu" / "T4.json"
        assert fichier.is_file()
        assert fichier.stat().st_size > 0
        assert journal_stop.read_text() == "stop called\n"  # trap did stop the session

    def test_telechargement_echoue_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "fail")

        assert resultat.returncode != 0
        assert "Done" not in resultat.stdout
        assert "ERREUR" in resultat.stdout
        assert journal_stop.read_text() == "stop called\n"  # trap runs even on failure

    def test_fichier_vide_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "empty")

        assert resultat.returncode != 0
        assert "Done" not in resultat.stdout
        assert "empty" in resultat.stdout.lower()
        assert journal_stop.read_text() == "stop called\n"

    def test_json_invalide_jamais_termine(self, environnement_test):
        tmp_path, environnement, journal_stop = environnement_test
        resultat = lancer_script(tmp_path, environnement, "invalid_json")

        assert resultat.returncode != 0
        assert "Done" not in resultat.stdout
        assert "valid JSON" in resultat.stdout
        assert journal_stop.read_text() == "stop called\n"
