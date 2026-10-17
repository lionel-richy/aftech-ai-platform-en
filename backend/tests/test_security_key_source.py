"""Checks STATICALLY that BACKEND_API_KEY only ever comes from the
environment (so, on Modal, exclusively from the "aftech-backend-secrets"
secret) — never a value hardcoded in the code."""

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _fichiers_python(dossier: Path):
    return [p for p in dossier.rglob("*.py") if "tests" not in p.parts and "__pycache__" not in p.parts]


def test_security_py_ne_lit_la_cle_que_depuis_os_environ():
    contenu = (BACKEND_DIR / "app" / "security.py").read_text(encoding="utf-8")
    assert 'os.environ.get("BACKEND_API_KEY")' in contenu
    # No hardcoded default value for this specific variable
    # (e.g. os.environ.get("BACKEND_API_KEY", "something")).
    assert not re.search(r'os\.environ\.get\("BACKEND_API_KEY",\s*["\']', contenu)


def test_aucun_fichier_backend_ne_contient_de_cle_codee_en_dur():
    motif_suspect = re.compile(r'BACKEND_API_KEY\s*=\s*["\'][^"\']+["\']')
    fichiers_suspects = []
    for fichier in _fichiers_python(BACKEND_DIR):
        contenu = fichier.read_text(encoding="utf-8")
        if motif_suspect.search(contenu):
            fichiers_suspects.append(str(fichier.relative_to(BACKEND_DIR)))
    assert fichiers_suspects == []


def test_modal_app_ne_definit_pas_backend_api_key_lui_meme():
    """Only the Modal secret "aftech-backend-secrets" must inject this key —
    modal_app.py must never set it itself (e.g. os.environ.setdefault).

    "BACKEND_API_KEY" can legitimately appear in a comment/docstring
    (e.g. the command "modal secret create ... BACKEND_API_KEY=<value>"):
    we check for the absence of a real ASSIGNMENT, not the total absence
    of the name.
    """
    contenu = (BACKEND_DIR / "app" / "modal_app.py").read_text(encoding="utf-8")
    motifs_interdits = [
        r'os\.environ\["BACKEND_API_KEY"\]\s*=',
        r"os\.environ\.setdefault\(\s*[\"']BACKEND_API_KEY[\"']",
        r'BACKEND_API_KEY\s*=\s*["\']',
    ]
    for motif in motifs_interdits:
        assert not re.search(motif, contenu), f"Suspicious assignment found ({motif})"
    assert "aftech-backend-secrets" in contenu
