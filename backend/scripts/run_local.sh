#!/bin/bash
# Runs the FastAPI backend locally, on this Mac.
#
# Important: this Mac has no CUDA GPU, so the RAG engine will start in
# "degraded" mode (/health -> ready=false): document search and
# /health / /documents / /metrics work, but /ask will return a clear 503
# error ("Backend unavailable") instead of crashing. This is the expected
# behavior locally; for a real, working /ask, you need to deploy on
# Modal (GPU).
set -e

cd "$(dirname "$0")/.."  # move into backend/

if [ -f ../.env ]; then
    echo "Loading variables from .env..."
    set -a
    source ../.env
    set +a
fi

export INDEX_DIR="${INDEX_DIR:-../data/indexes/aftech_documents}"

echo "Starting the backend on http://localhost:8000 (Ctrl+C to stop)..."
python3 -m uvicorn app.main:app --reload --port 8000
