"""Shared pytest fixtures.

Principle: we NEVER load the real models in tests (too slow, depends on
the network, needs a GPU for generation). We replace the RAG engine with
a test double (`FakeRagEngine`) via `app.dependency_overrides`, which
tests the API's real behavior (routes, validation, HTTP codes, errors)
without depending on Qwen/BGE-M3/FAISS.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allows "import app.main" when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("BACKEND_API_KEY", "test-key")

from app.document_manager import DocumentManager  # noqa: E402
from app.main import app, get_document_manager, get_engine  # noqa: E402
from app.metrics import metrics_store  # noqa: E402

API_KEY = os.environ["BACKEND_API_KEY"]


@pytest.fixture(autouse=True)
def _reset_metrics():
    """metrics_store is a singleton shared by the whole process: we reset
    it before every test so tests stay independent of execution order."""
    metrics_store.reset()
    yield


class FakeRagEngine:
    """Test double for the RAG engine: no model loaded, canned answers."""

    def __init__(self, *, ready: bool = True, ask_result: dict | None = None, ask_exception: Exception | None = None):
        self.ready = ready
        self._ask_result = ask_result
        self._ask_exception = ask_exception

    def health(self) -> dict:
        return {
            "status": "ok" if self.ready else "degraded",
            "ready": self.ready,
            "llm_model": "Qwen/Qwen3-4B-Instruct-2507",
            "embedding_model": "BAAI/bge-m3",
            "gpu": "Tesla L4" if self.ready else "unavailable",
            "vram_totale_octets": 23_609_475_072 if self.ready else None,
            "vram_utilisee_octets": 3_240_000_000 if self.ready else None,
            "documents_count": 3,
            "chunks_count": 353,
        }

    def documents(self) -> list[dict]:
        return [
            {
                "nom_fichier": "Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf",
                "pages": 15,
                "passages": 55,
                "hash_sha256": "deadbeef",
                "modele_embeddings": "BAAI/bge-m3",
                "date_index": "2026-09-29T17:40:06+00:00",
            }
        ]

    def ask(self, question: str, top_k: int = 8, response_language: str = "fr") -> dict:
        if self._ask_exception is not None:
            raise self._ask_exception
        return self._ask_result

    # --- Used by DocumentManager (see document_manager.py) ---

    embedder = None  # never used in tests that don't trigger real indexing

    def chunks_historiques(self, noms_affiches_geres: set[str]) -> list[dict]:
        return []

    def recharger_index(self, dossier_index: str) -> None:
        pass


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture
def make_client():
    """Builds a TestClient with a FakeRagEngine injected in place of the real engine."""
    clients: list[TestClient] = []

    def _make(fake_engine: FakeRagEngine) -> TestClient:
        app.dependency_overrides[get_engine] = lambda: fake_engine
        racine_store = tempfile.mkdtemp(prefix="aftech-test-documents-")
        gestionnaire = DocumentManager(racine_store, fake_engine)
        app.dependency_overrides[get_document_manager] = lambda: gestionnaire
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make

    app.dependency_overrides.clear()
    for client in clients:
        client.close()
