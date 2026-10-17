#!/bin/bash
# Runs the document assistant on Colab, start to finish.
#
# This script exists because "colab exec -f script.py" only sends the
# script itself: the files in data/samples/ must be uploaded by hand on
# every new session, otherwise the script finds them empty.
#
# Usage: ./scripts/run_document_assistant.sh [session_name]
set -e

SESSION="${1:-aftech-rag}"

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

# 3. Creating the remote folder then sending each document, one by one
#    (colab upload only handles one file at a time, not a whole folder)
echo "Preparing the remote data folder..."
echo "import os; os.makedirs('/content/data/samples', exist_ok=True)" | colab exec -s "$SESSION" --timeout 30

for fichier in data/samples/*.txt; do
    nom=$(basename "$fichier")
    echo "Sending $nom..."
    colab upload -s "$SESSION" "$fichier" "/content/data/samples/$nom"
done

# 4. Running the main script (large timeout: includes downloading the models)
echo "Starting the document assistant..."
colab exec -s "$SESSION" -f scripts/document_assistant.py --timeout 900

# 5. Immediate retrieval of the results.
# Important: the Colab VM can be recycled by Google at any time after the
# script finishes (the file would be lost if downloading it by hand is
# delayed). So we download it right away, in the same command.
echo "Downloading results..."
mkdir -p results/benchmarks
colab download -s "$SESSION" /content/results/benchmarks/rag_test.json results/benchmarks/rag_test.json
echo "Results retrieved in results/benchmarks/rag_test.json"
