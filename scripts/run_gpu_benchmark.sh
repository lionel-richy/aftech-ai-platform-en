#!/bin/bash
# Runs the reproducible GPU benchmark (ONE GPU at a time) on Colab.
#
# Usage: ./scripts/run_gpu_benchmark.sh <T4|L4|A100>
#
# Safety rules applied (see the project spec):
# - only one GPU accepted per run, never H100/G4/other;
# - refuses to start if ANOTHER "aftech-benchmark-*" session is already active;
# - never automatically retries a failed allocation;
# - never replaces the requested GPU with another one;
# - confirmation required before A100;
# - the session is stopped even on error (trap);
# - Colab usage (`colab usage`) is captured before/after when possible.
set -u  # (no global "set -e": we want to control each failure ourselves for the trap/clean stop)

GPU="${1:-}"

case "$GPU" in
    T4|L4|A100)
        ;;
    *)
        echo "Error: unknown or unsupported GPU at this stage: '${GPU}'."
        echo "Accepted values: T4, L4, A100 (H100 and G4 are not offered here)."
        echo "Usage: $0 <T4|L4|A100>"
        exit 1
        ;;
esac

GPU_MINUSCULE=$(echo "$GPU" | tr '[:upper:]' '[:lower:]')
SESSION="aftech-benchmark-${GPU_MINUSCULE}"

RESULTS_DIR="results/benchmarks/gpu"
OUTPUT_REMOTE="/content/${GPU}.json"
OUTPUT_LOCAL="${RESULTS_DIR}/${GPU}.json"
CONFIG_LOCAL="/tmp/benchmark_config_${GPU_MINUSCULE}.json"
CONFIG_REMOTE="/content/benchmark_config.json"
INSTALL_TIMING_LOCAL="/tmp/install_timing_${GPU_MINUSCULE}.json"
INSTALL_TIMING_REMOTE="/content/install_timing.json"

mkdir -p "$RESULTS_DIR"

echo "== GPU benchmark: $GPU (session '$SESSION') =="

# --- Confirmation required before A100 (the most expensive of the three) ---
if [ "$GPU" == "A100" ]; then
    echo "You are about to provision an A100 GPU — significantly more expensive than a T4/L4."
    read -r -p "Confirm? (type 'yes' to continue) " confirmation
    if [ "$confirmation" != "yes" ]; then
        echo "Cancelled."
        exit 0
    fi
fi

# --- Checks that no OTHER benchmark session is already active ---
# (requirement: only one benchmark GPU at a time)
AUTRES_SESSIONS=$(colab sessions 2>&1 | grep -i "aftech-benchmark-" | grep -v "$SESSION" || true)
if [ -n "$AUTRES_SESSIONS" ]; then
    echo "Error: another benchmark session appears to already be active:"
    echo "$AUTRES_SESSIONS"
    echo "Stop it first (colab stop -s <name>) before starting a new GPU."
    exit 1
fi

# --- Colab usage before (if the command is available locally) ---
if command -v colab >/dev/null 2>&1 && colab usage >/dev/null 2>&1; then
    colab usage > "${RESULTS_DIR}/${GPU}_usage_avant.txt" 2>&1
    echo "Colab usage BEFORE (see ${RESULTS_DIR}/${GPU}_usage_avant.txt):"
    cat "${RESULTS_DIR}/${GPU}_usage_avant.txt"
else
    echo "'colab usage' unavailable here: copy it manually if needed (see docs/MODAL_COST_SAFETY.md)."
fi

# --- Guaranteed cleanup, even on error ---
SESSION_CREEE=0
trap '
    if [ "$SESSION_CREEE" == "1" ]; then
        echo "Stopping session $SESSION (trap)..."
        colab stop -s "$SESSION" >/dev/null 2>&1 || true
    fi
    if command -v colab >/dev/null 2>&1 && colab usage >/dev/null 2>&1; then
        colab usage > "'"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt" 2>&1
        echo "Colab usage AFTER (see '"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt):"
        cat "'"${RESULTS_DIR}"'/'"${GPU}"'_usage_apres.txt"
    fi
' EXIT

# --- Session creation (ONE attempt only: no retry, no falling back to another GPU) ---
STATUT=$(colab status -s "$SESSION" 2>&1 || true)
if echo "$STATUT" | grep -qi "not found"; then
    echo "Creating GPU session $GPU..."
    if ! colab --auth oauth2 new -s "$SESSION" --gpu "$GPU"; then
        echo "Error: could not allocate GPU $GPU (quota, unavailability...)."
        echo "No automatic retry, and NO other GPU is used instead."
        exit 1
    fi
    SESSION_CREEE=1
else
    echo "Session already active, reusing it."
    SESSION_CREEE=1
fi

# --- Installing dependencies (timed when possible) ---
echo "Installing dependencies (requirements-colab.txt)..."
DEBUT_INSTALL=$(date +%s)
if ! colab install -s "$SESSION" -r requirements-colab.txt; then
    echo "Error while installing dependencies."
    exit 1
fi
FIN_INSTALL=$(date +%s)
echo "{\"temps_installation_secondes\": $((FIN_INSTALL - DEBUT_INSTALL))}" > "$INSTALL_TIMING_LOCAL"

# --- Sending ONLY the necessary files (not the whole project) ---
# rag_engine.py is self-contained (doesn't import schemas/security/metrics/main):
# only __init__.py and rag_engine.py are required on the "app" side.
echo "Sending necessary files..."
echo "import os; os.makedirs('/content/backend/app', exist_ok=True); os.makedirs('/content/data/indexes/aftech_documents', exist_ok=True)" \
    | colab exec -s "$SESSION" --timeout 30

colab upload -s "$SESSION" backend/app/__init__.py /content/backend/app/__init__.py
colab upload -s "$SESSION" backend/app/rag_engine.py /content/backend/app/rag_engine.py
colab upload -s "$SESSION" data/indexes/aftech_documents/index.faiss /content/data/indexes/aftech_documents/index.faiss
colab upload -s "$SESSION" data/indexes/aftech_documents/chunks.json /content/data/indexes/aftech_documents/chunks.json
colab upload -s "$SESSION" data/indexes/aftech_documents/manifest.json /content/data/indexes/aftech_documents/manifest.json

cat > "$CONFIG_LOCAL" <<EOF
{
  "gpu_attendu": "$GPU",
  "output": "$OUTPUT_REMOTE",
  "index_dir": "/content/data/indexes/aftech_documents",
  "repetitions": 3,
  "seed": 42,
  "install_timing_file": "$INSTALL_TIMING_REMOTE"
}
EOF
colab upload -s "$SESSION" "$CONFIG_LOCAL" "$CONFIG_REMOTE"
colab upload -s "$SESSION" "$INSTALL_TIMING_LOCAL" "$INSTALL_TIMING_REMOTE"

# --- GPU validation + running the benchmark ---
# (gpu_benchmark.py itself re-checks torch.cuda.get_device_name(0) against
# gpu_attendu and stops BEFORE writing anything if it doesn't match)
echo "Starting the benchmark (can take several minutes: loading Qwen + 6 questions x 3 repetitions)..."
if ! colab exec -s "$SESSION" -f scripts/gpu_benchmark.py --timeout 1800; then
    echo "ERREUR: the benchmark failed or was interrupted. See the output above."
    exit 1
fi

# --- Immediate download of the result (the VM can be recycled at any time) ---
# Important: "colab exec" can return a success code even if the remote
# Python script crashed (already observed). We therefore NEVER trust the
# exit code alone: the downloaded file is explicitly checked below
# (present, non-empty, valid JSON) before printing "Done".
echo "Downloading the result..."
if ! colab download -s "$SESSION" "$OUTPUT_REMOTE" "$OUTPUT_LOCAL"; then
    echo "ERREUR: downloading $OUTPUT_REMOTE failed."
    exit 1
fi

if [ ! -s "$OUTPUT_LOCAL" ]; then
    echo "ERREUR: $OUTPUT_LOCAL is missing or empty after download."
    exit 1
fi

ERREUR_JSON="/tmp/erreur_json_${GPU_MINUSCULE}.txt"
if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$OUTPUT_LOCAL" 2>"$ERREUR_JSON"; then
    echo "ERREUR: $OUTPUT_LOCAL does not contain valid JSON:"
    cat "$ERREUR_JSON"
    rm -f "$ERREUR_JSON"
    exit 1
fi
rm -f "$ERREUR_JSON"

echo "Done: valid (JSON) result in $OUTPUT_LOCAL"
# The "trap" above stops the session and captures usage afterwards, in
# every case (success or exit 1 on one of the errors above).
