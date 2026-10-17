"""Verifies that the Modal `availability` function (backend/app/modal_app.py):
- actually runs without error (like test_modal_app_loads.py for web());
- responds 200 on GET /availability;
- NEVER imports app.main nor app.rag_engine — so it never loads
  Qwen/BGE-M3 and has no chance of touching a GPU.

Context (see docs/exchange with the user, "Part 2"): the frontend must be
able to poll the API's availability in a loop (every 30s) WITHOUT ever
resetting the scale-to-zero timer of web()'s GPU container. This function
exists precisely for that — this test proves it's actually isolated from
the AI engine, not just "on paper".

Skipped if the `modal` package isn't installed (like test_modal_app_loads.py)."""

import sys
from pathlib import Path

import pytest

modal = pytest.importorskip("modal")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _importer_modal_app():
    sys.path.insert(0, str(BACKEND_DIR))
    from modal.cli.import_refs import ImportRef, import_file_or_module

    ref = ImportRef(file_or_module="app/modal_app.py", object_path="", use_module_mode=False)
    return import_file_or_module(ref)


def test_availability_function_executes_and_returns_fastapi_app(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    module = _importer_modal_app()

    resultat = module.availability.local()

    from fastapi import FastAPI

    assert isinstance(resultat, FastAPI)


def test_availability_endpoint_returns_ok_status(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)
    module = _importer_modal_app()

    from fastapi.testclient import TestClient

    client = TestClient(module.availability.local())
    reponse = client.get("/availability")

    assert reponse.status_code == 200
    assert reponse.json()["status"] == "ok"


def test_availability_ne_touche_jamais_au_moteur_ia(monkeypatch):
    """Proof that /availability is isolated from the GPU: running this
    function must NEVER import app.main (where the lifespan that loads
    Qwen/BGE-M3 lives) nor app.rag_engine (the engine itself)."""
    monkeypatch.chdir(BACKEND_DIR)
    for nom_module in ("app.main", "app.rag_engine"):
        sys.modules.pop(nom_module, None)

    module = _importer_modal_app()
    module.availability.local()

    assert "app.main" not in sys.modules
    assert "app.rag_engine" not in sys.modules


def test_availability_est_bien_separee_de_web_gpu():
    """web() (GPU) and availability() (CPU) must be two DISTINCT Modal
    functions — never the same one, otherwise polling either would reset
    the same scale-to-zero timer."""
    module = _importer_modal_app()
    assert module.web is not module.availability


def test_decorateur_de_availability_ne_porte_aucune_configuration_gpu():
    """Reads modal_app.py's SOURCE: the @app.function(...) block preceding
    `def availability():` must contain no gpu= parameter, unlike web()'s."""
    source = (BACKEND_DIR / "app" / "modal_app.py").read_text(encoding="utf-8")
    avant_availability, _, apres = source.partition("def availability():")
    bloc_decorateur_availability = avant_availability.rsplit("@app.function(", 1)[-1]

    assert "gpu=" not in bloc_decorateur_availability
    # And we check the test itself isn't looking at the wrong function:
    # the web() block just before MUST contain gpu= (otherwise web()'s
    # definition changed and this test no longer protects anything).
    avant_web, _, _ = source.partition("def web():")
    bloc_decorateur_web = avant_web.rsplit("@app.function(", 1)[-1]
    assert "gpu=" in bloc_decorateur_web
