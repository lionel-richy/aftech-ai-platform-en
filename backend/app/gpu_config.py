"""Modal GPU selection rule — isolated in a module with no dependency on
`modal`, so it stays testable even when that package isn't installed
(e.g. on this Mac, where only the degraded no-GPU mode is tested locally).

Based on the real benchmark (results/benchmarks/gpu/) for Qwen3-4B-Instruct-2507
in 4-bit:
    T4   : 7.6 tokens/s,  22.48 s/answer, peak 4.64 GB
    L4   : 12.4 tokens/s, 15.33 s/answer, peak 3.02 GB
    A100 : 13.2 tokens/s, 15.06 s/answer, peak 3.02 GB
L4 is nearly as fast as A100 for this model, but noticeably cheaper: it's
the recommended GPU for the demo. T4 remains the budget profile. A100 is
explicitly disallowed (no measured gain, higher cost).
"""

import os

GPU_TYPES_AUTORISES = ("T4", "L4")
GPU_TYPE_DEFAUT = "L4"


def resoudre_gpu_type(valeur_env: str | None = None) -> str:
    """Determines which GPU to use, rejecting any disallowed value.

    `valeur_env` allows testing without depending on the real environment
    variable; in normal use, Modal reads MODAL_GPU_TYPE directly from the
    environment.
    """
    brut = valeur_env if valeur_env is not None else os.environ.get("MODAL_GPU_TYPE", GPU_TYPE_DEFAUT)
    valeur = brut.strip()
    if valeur not in GPU_TYPES_AUTORISES:
        raise ValueError(
            f"MODAL_GPU_TYPE={valeur!r} is not allowed. Accepted values: "
            f"{GPU_TYPES_AUTORISES}. A100 is explicitly disallowed for Qwen 4B "
            "(no measured gain, higher cost — see the GPU benchmark)."
        )
    return valeur
