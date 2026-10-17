#!/bin/bash
# Runs the PDF document assistant on Colab, start to finish.
#
# As with run_document_assistant.sh: "colab exec -f script.py" only sends
# the script itself, so the PDF must be uploaded by hand on every new
# session, otherwise the script won't find it.
#
# Usage: ./scripts/run_pdf_assistant.sh [session_name]
set -e

SESSION="${1:-aftech-pdf}"
PDF_LOCAL="data/sample_pdf/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"
PDF_REMOTE="/content/Epic_AI_Platform_Model_Infrastructure_AFTECH_Terre_a_Terre_v1.pdf"

echo "== Colab session: $SESSION =="

# 1. Check whether the session already exists; otherwise create a new one (T4 by default)
# Note: "colab status" always returns exit code 0, even when the session
# doesn't exist (known bug in version 0.6.0) — so we look at the message
# text instead of the exit code.
STATUT=$(colab status -s "$SESSION" 2>&1 || true)
if echo "$STATUT" | grep -qi "not found"; then
    echo "No session found, creating a new T4 GPU session..."
    colab --auth oauth2 new -s "$SESSION" --gpu T4
else
    echo "Session already active, reusing it."
fi

# 2. Installing Python dependencies on the remote machine
echo "Installing dependencies (requirements-colab.txt)..."
colab install -s "$SESSION" -r requirements-colab.txt

# 3. Sending the PDF to /content (location expected by scripts/pdf_assistant.py)
echo "Sending the PDF..."
colab upload -s "$SESSION" "$PDF_LOCAL" "$PDF_REMOTE"

# 4. Running the main script (large timeout: includes downloading the models)
echo "Starting the PDF document assistant..."
colab exec -s "$SESSION" -f scripts/pdf_assistant.py --timeout 900

# 5. Immediate retrieval of the results.
# Important: the Colab VM can be recycled by Google at any time after the
# script finishes (the file would be lost if downloading it by hand is
# delayed). So we download it right away, in the same command.
echo "Downloading results..."
mkdir -p results/benchmarks
colab download -s "$SESSION" /content/results/benchmarks/pdf_rag_test.json results/benchmarks/pdf_rag_test.json
echo "Results retrieved in results/benchmarks/pdf_rag_test.json"
