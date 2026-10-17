#!/bin/bash
# Runs the multi-PDF document assistant on Colab, start to finish:
# session -> dependencies -> PDFs -> index (built or reused) -> test
# questions -> retrieving the index and the results back to the Mac.
#
# As with the other run_*.sh scripts: "colab exec -f script.py" only sends
# the script itself, so the PDFs (and the local index, if it already
# exists) must be uploaded by hand.
#
# Usage: ./scripts/run_multi_document_assistant.sh [session_name]
set -e

SESSION="${1:-aftech-documents}"

DOSSIER_PDF_LOCAL="data/documents"
DOSSIER_INDEX_LOCAL="data/indexes/aftech_documents"
DOSSIER_INDEX_REMOTE="/content/data/indexes/aftech_documents"
ARCHIVE_LOCALE="/tmp/aftech_documents.tar.gz"

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

# 3. Compressing then sending the PDFs to Colab
# (colab upload only handles one file at a time, not a whole folder)
echo "Compressing $DOSSIER_PDF_LOCAL..."
tar -czf "$ARCHIVE_LOCALE" -C data documents

echo "Sending the PDF archive..."
colab upload -s "$SESSION" "$ARCHIVE_LOCALE" /content/aftech_documents.tar.gz

echo "Extracting the archive on the remote machine..."
echo "import tarfile, os; os.makedirs('/content/data', exist_ok=True); tarfile.open('/content/aftech_documents.tar.gz').extractall('/content/data', filter='data')" \
    | colab exec -s "$SESSION" --timeout 60

rm -f "$ARCHIVE_LOCALE"

# 4. Sending the local index, if it already exists, to attempt reuse
# (build_document_index.py will compare the PDF hashes to decide whether
# a rebuild is needed).
if [ -f "$DOSSIER_INDEX_LOCAL/manifest.json" ]; then
    echo "Local index found, sending it to Colab to attempt reuse..."
    echo "import os; os.makedirs('$DOSSIER_INDEX_REMOTE', exist_ok=True)" | colab exec -s "$SESSION" --timeout 30
    for fichier in index.faiss chunks.json manifest.json; do
        if [ -f "$DOSSIER_INDEX_LOCAL/$fichier" ]; then
            colab upload -s "$SESSION" "$DOSSIER_INDEX_LOCAL/$fichier" "$DOSSIER_INDEX_REMOTE/$fichier"
        fi
    done
else
    echo "No existing local index: it will be built from scratch."
fi

# 5. Building (or reusing, if the PDFs haven't changed) the index
echo "Building/reusing the index..."
colab exec -s "$SESSION" -f scripts/build_document_index.py --timeout 1800

# 6. Test questions against the multi-PDF index
echo "Running the test questions..."
colab exec -s "$SESSION" -f scripts/query_document_index.py --timeout 1800

# 7. Immediate retrieval of the index and the results.
# Important: the Colab VM can be recycled by Google at any time after the
# script finishes (the files would be lost if downloading them by hand is
# delayed).
echo "Downloading the index and the results..."
mkdir -p "$DOSSIER_INDEX_LOCAL" results/benchmarks
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/index.faiss" "$DOSSIER_INDEX_LOCAL/index.faiss"
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/chunks.json" "$DOSSIER_INDEX_LOCAL/chunks.json"
colab download -s "$SESSION" "$DOSSIER_INDEX_REMOTE/manifest.json" "$DOSSIER_INDEX_LOCAL/manifest.json"
colab download -s "$SESSION" /content/results/benchmarks/multi_document_test.json results/benchmarks/multi_document_test.json

echo "Done: index in $DOSSIER_INDEX_LOCAL/, results in results/benchmarks/multi_document_test.json"
