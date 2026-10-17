"""Modal deployment of the FastAPI backend (with a GPU attached).

This file does NOT launch anything by itself: it declares the
configuration. The actual deployment happens via
backend/scripts/modal_deploy.sh (deliberately NOT automatic — see
docs/MODAL_COST_SAFETY.md).

Run from the backend/ folder (so "app" is importable as a top-level
Python module):
    cd backend && modal deploy app/modal_app.py

GPU choice — based on the real benchmark (results/benchmarks/gpu/):
  T4   : 7.6 tokens/s,  22.48 s/answer, peak 4.64 GB
  L4   : 12.4 tokens/s, 15.33 s/answer, peak 3.02 GB
  A100 : 13.2 tokens/s, 15.06 s/answer, peak 3.02 GB
L4 is nearly as fast as A100 for Qwen 4B, but noticeably cheaper: it's the
recommended GPU for the demo. T4 remains the budget profile. A100 brings
NO benefit for this model and is explicitly disallowed below
(MODAL_GPU_TYPE can only be "T4" or "L4").

Cost/safety parameters chosen:
- L4 GPU by default; MODAL_GPU_TYPE="T4" for the budget profile. Any other
  value (including "A100") fails the deployment immediately, with a clear
  message, rather than allowing it.
- min_containers=0: no container runs (so no cost) while nobody is calling
  the API.
- max_containers=1: only one GPU container at a time (no cost runaway if
  several requests arrive at once).
- scaledown_window=300: the container shuts down 5 minutes after the last
  request (not immediately, to avoid reloading the model on every call;
  not indefinitely either).
- No permanent service: no extra @app.function running continuously, a
  single entry point (web), itself scale-to-zero.

These figures (the exact signature of the Modal parameters) were verified
against the actually installed `modal` package (version 1.6.1), not
assumed from the online documentation.
"""

import os

import modal

from app.gpu_config import resoudre_gpu_type

GPU_TYPE = resoudre_gpu_type()
SCALEDOWN_WINDOW_SECONDES = 300
MAX_CONTAINERS = 1
MIN_CONTAINERS = 0

app = modal.App("aftech-ai-platform")

# Hugging Face cache (Qwen + BGE-M3 weights): persistent across container
# restarts, so we don't re-download several GB on every cold start.
hf_cache_volume = modal.Volume.from_name("aftech-hf-cache", create_if_missing=True)

# Documents uploaded from the Library (PDFs, registry, dynamically
# rebuilt index) — SEPARATE from the index baked into `image` below,
# which stays frozen (the 4 historical PDFs). Volume created once,
# outside the code:
#   modal volume create aftech-document-store
DOCUMENT_STORE_VOLUME_NAME = "aftech-document-store"
document_store_volume = modal.Volume.from_name(DOCUMENT_STORE_VOLUME_NAME, create_if_missing=True)
DOCUMENT_STORE_MOUNT = "/data/document-store"

# Modal secret holding BACKEND_API_KEY (and any other sensitive value).
# Created once, outside the code, via:
#   modal secret create aftech-backend-secrets BACKEND_API_KEY=<value>
# required_keys: Modal refuses the deployment if the secret exists but
# doesn't contain BACKEND_API_KEY — this is the ONLY allowed source for
# this key (never hardcoded, never another environment variable).
backend_secret = modal.Secret.from_name("aftech-backend-secrets", required_keys=["BACKEND_API_KEY"])

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    # Already-built index (scripts/build_document_index.py): baked into
    # the image, not recomputed on Modal.
    .add_local_dir(
        "../data/indexes/aftech_documents",
        remote_path="/app/data/indexes/aftech_documents",
    )
    # Application code (the "app" package itself).
    .add_local_python_source("app")
)


@app.function(
    image=image,
    gpu=GPU_TYPE,
    volumes={
        "/root/.cache/huggingface": hf_cache_volume,
        DOCUMENT_STORE_MOUNT: document_store_volume,
    },
    secrets=[backend_secret],
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW_SECONDES,
)
@modal.asgi_app()
def web():
    index_baked = "/app/data/indexes/aftech_documents"
    index_sur_volume = os.path.join(DOCUMENT_STORE_MOUNT, "index", "current")
    # Once at least one document has been added/removed via the Library,
    # index/current exists on the Volume and becomes the active version
    # (it then contains the 4 historical PDFs + the new ones) — otherwise
    # (very first startup, before this feature has ever been used), we
    # start from the index baked into the image, unchanged.
    index_actif = (
        index_sur_volume if os.path.isfile(os.path.join(index_sur_volume, "index.faiss")) else index_baked
    )

    # Startup metric (no sensitive content): visible in `modal app logs`.
    print(f"[modal] starting a container — GPU={GPU_TYPE}, index={index_actif}")

    os.environ.setdefault("INDEX_DIR", index_actif)
    os.environ.setdefault("DOCUMENT_STORE_DIR", DOCUMENT_STORE_MOUNT)
    os.environ.setdefault("DOCUMENT_STORE_VOLUME_NAME", DOCUMENT_STORE_VOLUME_NAME)

    from app.main import app as fastapi_app

    return fastapi_app


# MINIMAL image for availability: no ML dependency at all (no torch, no
# transformers, no faiss) — just FastAPI, for a near-instant startup,
# fully independent from `image` (web()'s, above).
#
# add_local_python_source("app") is needed here too: Modal imports the
# WHOLE modal_app.py file (so `from app.gpu_config import
# resoudre_gpu_type` above, used by web()) into the container of EVERY
# function it contains, including availability() — without this,
# ModuleNotFoundError("No module named 'app'") crash-loops this container
# (a real bug hit during the v4 deployment, fixed here). app.gpu_config
# only does "import os": no ML dependency is pulled in.
image_disponibilite = (
    modal.Image.debian_slim(python_version="3.11").pip_install("fastapi").add_local_python_source("app")
)


@app.function(
    image=image_disponibilite,
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
)
@modal.asgi_app()
def availability():
    """SEPARATE Modal function, CPU only (no `gpu=` here): its only role
    is to answer "the API is reachable", without ever importing app.main
    (which loads Qwen/BGE-M3 via the lifespan) or touching the GPU.

    Explicit goal: the frontend can poll THIS function in a loop (every
    30s) WITHOUT ever resetting the scale-to-zero timer of web()'s GPU
    container — the two functions are fully independent containers, each
    with its own Modal lifecycle."""
    from fastapi import FastAPI

    api_disponibilite = FastAPI()

    @api_disponibilite.get("/availability")
    def etat_disponibilite() -> dict:
        return {"status": "ok", "service": "aftech-ai-platform-availability"}

    return api_disponibilite
