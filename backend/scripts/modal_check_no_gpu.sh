#!/bin/bash
# Checks that NO GPU container is currently running (so no cost is being incurred).
set -e

echo "== Containers currently running on Modal =="
SORTIE=$(modal container list 2>&1)
echo "$SORTIE"

echo ""
if echo "$SORTIE" | grep -qi "aftech-ai-platform"; then
    echo "WARNING: at least one 'aftech-ai-platform' container appears to be active."
    echo "An active GPU container is billed. Use modal_stop.sh if needed."
else
    echo "OK: no active 'aftech-ai-platform' container — no GPU cost currently incurred."
fi
