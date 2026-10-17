#!/bin/bash
# Modal deployment — WITHOUT AUTOMATIC EXECUTION.
#
# By default, this script prints the chosen GPU, the theoretical cost, the
# shutdown parameters, the required secrets and the exact command, but
# deploys NOTHING. Re-run with --yes to actually deploy.
set -e

GPU_TYPE="${MODAL_GPU_TYPE:-L4}"
SCALEDOWN=300
MAX_CONTAINERS=1
MIN_CONTAINERS=0

# Same rule as backend/app/gpu_config.py: A100 is explicitly forbidden for
# Qwen 4B (real benchmark: no gain vs L4, higher cost). We check it HERE
# too, to fail before even trying modal deploy.
case "$GPU_TYPE" in
    T4|L4)
        ;;
    *)
        echo "ERROR: MODAL_GPU_TYPE='$GPU_TYPE' is not allowed."
        echo "Accepted values: T4, L4. A100 is explicitly forbidden for Qwen 4B"
        echo "(real benchmark: no gain vs L4, higher cost — see results/benchmarks/gpu/recommendation.md)."
        exit 1
        ;;
esac

cat <<EOF
=== Modal deployment — aftech-ai-platform ===

Chosen GPU           : $GPU_TYPE (recommended: L4 — nearly as fast as A100 for Qwen 4B, cheaper; T4 = budget profile)
Min/max containers   : $MIN_CONTAINERS / $MAX_CONTAINERS (scale-to-zero, never more than one GPU container at a time)
Automatic shutdown   : $SCALEDOWN seconds of inactivity before the container is shut down
Required secret       : aftech-backend-secrets (must contain BACKEND_API_KEY)
                        -> create it once, BEFORE deploying:
                           modal secret create aftech-backend-secrets BACKEND_API_KEY=<your-key>

Theoretical cost (estimate — check the exact pricing at modal.com/pricing
at deployment time, prices may change):
  - \$0 as long as no request comes in (min_containers=0, no container
    running permanently).
  - Billed only while a $GPU_TYPE GPU container is active: from the
    first call until $SCALEDOWN seconds after the last call received.
  - max_containers=$MAX_CONTAINERS: only one GPU container at a time, so the
    bill can't spiral even if several requests arrive at the same time
    (they will wait their turn instead of opening a 2nd GPU).

Exact command that will be run:
  cd backend && modal deploy app/modal_app.py

EOF

if [ "$1" == "--yes" ]; then
    echo "Deployment confirmed (--yes): running..."
    cd "$(dirname "$0")/.."
    modal deploy app/modal_app.py
else
    echo "Nothing was deployed."
    echo "To actually deploy: ./backend/scripts/modal_deploy.sh --yes"
fi
