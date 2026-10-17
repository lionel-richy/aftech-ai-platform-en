"""Verifies that backend/app/modal_app.py not only LOADS, but that the
body of the web() function actually RUNS without error.

Real bug encountered: a missing `import os` caused NO error when the
module loaded (only `GPU_TYPE = resoudre_gpu_type()` runs at that point)
— the NameError only appeared when web() actually ran, i.e. once
deployed on Modal. This test calls `.local()` to really execute the
function body, the way Modal would inside the container.

Skipped if the `modal` package isn't installed (not a dependency of the
lightweight test venv used for the rest of the suite).
"""

import sys
from pathlib import Path

import pytest

modal = pytest.importorskip("modal")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_web_function_executes_without_nameerror(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    from modal.cli.import_refs import ImportRef, import_file_or_module

    ref = ImportRef(file_or_module="app/modal_app.py", object_path="", use_module_mode=False)
    module = import_file_or_module(ref)

    resultat = module.web.local()

    # web() must return the real FastAPI app (not crash before getting there).
    from fastapi import FastAPI

    assert isinstance(resultat, FastAPI)
