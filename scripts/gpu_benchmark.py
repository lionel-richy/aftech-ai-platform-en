"""
Reproducible GPU benchmark (T4 / L4 / A100) for AFTECH.

Compares the SAME pipeline (Qwen3-4B-Instruct-2507 in 4-bit + BGE-M3 + FAISS,
same questions, same generation parameters, same seed) across different
Colab GPUs. Directly reuses backend/app/rag_engine.py — the API's engine —
as the single source of truth: no parameter can diverge between the tested
GPUs, since it's literally the same code running.

Safety (explicit requirement): if the GPU actually obtained does NOT match
the requested GPU, the script stops IMMEDIATELY, before writing anything —
never a "T4.json" file obtained on a different GPU.

Usage (on Colab, via colab exec):
    python scripts/gpu_benchmark.py --gpu-attendu T4 --output results/benchmarks/gpu/T4.json
"""

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Default Colab folder where run_gpu_benchmark.sh sends backend/app/*.py
# (see "send only the needed files" in this same script).
DOSSIER_BACKEND_COLAB_DEFAUT = "/content/backend"


def determiner_dossier_backend(fichier_script: str | None, racine_colab: str = DOSSIER_BACKEND_COLAB_DEFAUT) -> Path:
    """Determines the folder containing the "app" package (backend/) to add to sys.path.

    - Run normally (`python scripts/gpu_benchmark.py`): `__file__` is
      defined, we go up to the project root then "backend".
    - Run via `colab exec`: the code is passed to `exec()` in an
      already-started Jupyter kernel, where `__file__` does NOT exist
      (NameError if accessed directly) — in that case we use /content/backend.

    Pure function (no access to `__file__` here): testable without depending
    on the real execution context, see tests/test_gpu_benchmark_helpers.py.
    """
    if fichier_script:
        return Path(fichier_script).resolve().parents[1] / "backend"
    return Path(racine_colab)


# Lets us import backend/app/rag_engine.py: the SAME engine as the API.
# globals().get("__file__") rather than "__file__" directly: accessing a
# missing name raises NameError even in a plain expression, whereas
# globals().get(...) returns None cleanly (the "colab exec" case).
sys.path.insert(0, str(determiner_dossier_backend(globals().get("__file__"))))

GPU_ATTENDUS_VALIDES = ("T4", "L4", "A100")

# Identical questions for every GPU (explicit requirement: never vary them
# depending on which GPU is being tested). Left in French on purpose: these
# are real functional benchmark inputs run against the actual indexed
# documents — translating them could change what gets retrieved.
QUESTIONS = [
    "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
    "Quel document contient les informations relatives à Azure ?",
    "Quel est l'objectif principal de l'EU AI Act ?",
    "Résume le sujet principal du document Accompagnement2004.pdf.",
    "Quel document parle de vLLM ?",
    "Quel est le nom du directeur financier d'AFTECH ?",
]

TOP_K = 8
REPETITIONS_DEFAUT = 3
SEED_DEFAUT = 42


def valider_gpu_attendu(gpu_attendu: str, gpu_obtenu: str) -> bool:
    """Compares the GPU actually obtained (e.g. "Tesla T4", "NVIDIA A100-SXM4-40GB")
    to the requested GPU (e.g. "T4", "A100").

    PURE function (no GPU dependency): tested without hardware in
    backend/tests or tests/ (see the benchmark's test scripts).
    """
    if not gpu_obtenu:
        return False
    return gpu_attendu.strip().upper() in gpu_obtenu.strip().upper()


CONFIG_PATH_DEFAUT = "/content/benchmark_config.json"


def fusionner_config_fichier(args, parser):
    """"colab exec" NEVER passes custom arguments (already seen on the other
    scripts): if --gpu-attendu/--output aren't supplied on the command line,
    we read them from a small JSON file uploaded by run_gpu_benchmark.sh
    (e.g. /content/benchmark_config.json).

    PURE function (touches nothing global): testable without a GPU, without
    a real file (we pass it a dict directly in the tests).
    """
    if args.gpu_attendu and args.output:
        return args  # everything supplied on the command line, nothing to fill in

    if not os.path.isfile(args.config):
        parser.error(
            f"--gpu-attendu and --output are required (directly, or via the "
            f"configuration file {args.config}, missing here)."
        )

    with open(args.config, encoding="utf-8") as f:
        config_fichier = json.load(f)

    args.gpu_attendu = args.gpu_attendu or config_fichier.get("gpu_attendu")
    args.output = args.output or config_fichier.get("output")
    args.index_dir = config_fichier.get("index_dir", args.index_dir)
    args.repetitions = config_fichier.get("repetitions", args.repetitions)
    args.seed = config_fichier.get("seed", args.seed)
    args.install_timing_file = config_fichier.get("install_timing_file", args.install_timing_file)

    if not args.gpu_attendu or not args.output:
        parser.error("Incomplete configuration: gpu_attendu and output are required.")

    return args


def parse_args():
    parser = argparse.ArgumentParser(description="Reproducible AFTECH GPU benchmark.")
    parser.add_argument("--gpu-attendu", choices=GPU_ATTENDUS_VALIDES, default=None)
    parser.add_argument("--output", default=None, help="Path of the output JSON file")
    parser.add_argument("--index-dir", default="data/indexes/aftech_documents")
    parser.add_argument("--repetitions", type=int, default=REPETITIONS_DEFAUT)
    parser.add_argument("--seed", type=int, default=SEED_DEFAUT)
    parser.add_argument(
        "--install-timing-file",
        default=None,
        help="JSON file (written by run_gpu_benchmark.sh) containing the dependency install time, if measured.",
    )
    parser.add_argument(
        "--config",
        default=CONFIG_PATH_DEFAUT,
        help="Configuration JSON file, used if --gpu-attendu/--output are absent (colab exec case).",
    )
    # parse_known_args (not parse_args): "colab exec" runs this code in an
    # already-started Jupyter kernel, whose own arguments (e.g. "-f
    # <connection-file>") are visible here. They're silently ignored instead
    # of crashing on them (same bug already seen in the other scripts).
    args, _ = parser.parse_known_args()
    return fusionner_config_fichier(args, parser)


def executer_commande(commande: list[str], timeout=10):
    try:
        resultat = subprocess.run(commande, capture_output=True, text=True, timeout=timeout)
        return resultat.stdout.strip() if resultat.returncode == 0 else None
    except Exception:
        return None


def obtenir_version_pilote_nvidia():
    sortie = executer_commande(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    return sortie.splitlines()[0].strip() if sortie else None


def obtenir_ram_systeme_go():
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for ligne in f:
                if ligne.startswith("MemTotal:"):
                    ko = int(ligne.split()[1])
                    return round(ko / (1024**2), 2)
    except Exception:
        pass
    return None


def obtenir_nom_cpu():
    try:
        with open("/proc/cpuinfo") as f:
            for ligne in f:
                if ligne.lower().startswith("model name"):
                    return ligne.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine() or None


class EchantillonneurGPU:
    """Samples GPU utilization/power via nvidia-smi in the background during
    a generation. Silently disables itself if nvidia-smi is unavailable
    (these metrics are explicitly "if available" in the spec)."""

    def __init__(self, intervalle_secondes: float = 0.5):
        self.intervalle_secondes = intervalle_secondes
        self._stop = threading.Event()
        self._thread = None
        self.utilisations: list[float] = []
        self.puissances_watts: list[float] = []
        self.disponible = executer_commande(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"]) is not None

    def _boucle(self):
        while not self._stop.is_set():
            sortie = executer_commande(
                ["nvidia-smi", "--query-gpu=utilization.gpu,power.draw", "--format=csv,noheader,nounits"], timeout=5
            )
            if sortie:
                try:
                    partie_util, partie_puissance = sortie.split(",")
                    self.utilisations.append(float(partie_util.strip()))
                    self.puissances_watts.append(float(partie_puissance.strip()))
                except ValueError:
                    pass
            self._stop.wait(self.intervalle_secondes)

    def __enter__(self):
        if self.disponible:
            self._thread = threading.Thread(target=self._boucle, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def resume(self) -> dict:
        return {
            "utilisation_gpu_moyenne_pourcent": round(statistics.mean(self.utilisations), 1) if self.utilisations else None,
            "puissance_moyenne_watts": round(statistics.mean(self.puissances_watts), 1) if self.puissances_watts else None,
            "puissance_max_watts": round(max(self.puissances_watts), 1) if self.puissances_watts else None,
        }


def mesurer_premier_token(engine, question: str) -> dict:
    """Measures the time before the first generated token (TTFT), via a
    DEDICATED, separate streaming call (same model, same prompt, same
    parameters), so the generation path shared with the API is never
    modified."""
    try:
        from transformers import TextIteratorStreamer
    except Exception as exc:
        return {"disponible": False, "raison": str(exc)}

    from app.rag_engine import MAX_NEW_TOKENS, SYSTEM_PROMPT

    passages = engine._rechercher_passages(question, TOP_K)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": engine._construire_prompt(question, passages)},
    ]
    inputs = engine.tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(engine.model.device)

    streamer = TextIteratorStreamer(engine.tokenizer, skip_special_tokens=True)
    kwargs = dict(inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, streamer=streamer)

    debut = time.perf_counter()
    thread = threading.Thread(target=engine.model.generate, kwargs=kwargs)
    thread.start()

    temps_premier_token = None
    for _ in streamer:
        if temps_premier_token is None:
            temps_premier_token = time.perf_counter() - debut
    thread.join()

    return {"disponible": True, "temps_premier_token_secondes": temps_premier_token}


def agreger(valeurs: list) -> dict | None:
    valeurs = [v for v in valeurs if v is not None]
    if not valeurs:
        return None
    return {
        "moyenne": statistics.mean(valeurs),
        "mediane": statistics.median(valeurs),
        "minimum": min(valeurs),
        "maximum": max(valeurs),
        "ecart_type": statistics.stdev(valeurs) if len(valeurs) > 1 else 0.0,
    }


def executer_un_appel(engine, torch_module, question: str) -> tuple[dict | None, list[dict]]:
    """A single run (search + generation + validation). Returns
    (measurement, errors) — measurement is None if a CUDA/memory error occurred."""
    torch_module.cuda.reset_peak_memory_stats()
    memoire_avant = torch_module.cuda.memory_allocated()

    try:
        with EchantillonneurGPU() as echantillonneur:
            debut_total = time.perf_counter()
            resultat = engine.ask(question, top_k=TOP_K)
            temps_total_mesure = time.perf_counter() - debut_total
        stats_gpu = echantillonneur.resume()
    except torch_module.cuda.OutOfMemoryError as exc:
        return None, [{"type": "cuda_out_of_memory", "message": str(exc)}]
    except RuntimeError as exc:
        return None, [{"type": "cuda_runtime_error", "message": str(exc)}]

    memoire_pic = torch_module.cuda.max_memory_allocated()
    temps_generation = resultat["timings"]["generation_secondes"]

    mesure = {
        "status": resultat["status"],
        "answer": resultat["answer"],
        "tokens_entree": resultat["tokens_entree"],
        "tokens_generes": resultat["tokens_generes"],
        "tokens_par_seconde": (resultat["tokens_generes"] / temps_generation) if temps_generation > 0 else None,
        "temps_recherche_secondes": resultat["timings"]["recherche_secondes"],
        "temps_generation_secondes": temps_generation,
        "temps_total_secondes": temps_total_mesure,
        "memoire_gpu_avant_octets": memoire_avant,
        "memoire_gpu_pic_octets": memoire_pic,
        **stats_gpu,
    }
    return mesure, []


def main():
    args = parse_args()

    import torch

    torch.manual_seed(args.seed)

    print(f"Requested GPU: {args.gpu_attendu}")
    if not torch.cuda.is_available():
        print("ERROR: no CUDA GPU detected. Stopping immediately, nothing written.", file=sys.stderr)
        sys.exit(1)

    gpu_obtenu = torch.cuda.get_device_name(0)
    print(f"Obtained GPU: {gpu_obtenu}")

    if not valider_gpu_attendu(args.gpu_attendu, gpu_obtenu):
        print(
            f"ERROR: the obtained GPU ('{gpu_obtenu}') does not match the requested GPU "
            f"('{args.gpu_attendu}'). Stopping immediately, NO file written.",
            file=sys.stderr,
        )
        sys.exit(1)

    avertissements: list[str] = []
    if args.install_timing_file and os.path.isfile(args.install_timing_file):
        with open(args.install_timing_file, encoding="utf-8") as f:
            temps_installation = json.load(f).get("temps_installation_secondes")
    else:
        temps_installation = None
        avertissements.append(
            "Dependency install time not measured (--install-timing-file file absent)."
        )

    avertissements.append(
        "Deterministic generation (do_sample=False) limits but does not guarantee "
        "bit-exact reproducibility across different GPUs/CUDA kernel versions."
    )

    vram_totale_octets = torch.cuda.get_device_properties(0).total_memory
    memoire_gpu_avant_chargement = torch.cuda.memory_allocated()

    from app import rag_engine
    from app.rag_engine import RagEngine

    engine = RagEngine(index_dir=args.index_dir)
    engine.load()

    if not engine.ready:
        print(f"ERROR loading the RAG engine: {engine.error}", file=sys.stderr)
        sys.exit(1)

    memoire_gpu_apres_chargement = torch.cuda.memory_allocated()

    import sentence_transformers
    import transformers
    import bitsandbytes

    configuration = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "gpu_demande": args.gpu_attendu,
        "gpu_obtenu": gpu_obtenu,
        "vram_totale_octets": vram_totale_octets,
        "version_cuda": torch.version.cuda,
        "version_pilote_nvidia": obtenir_version_pilote_nvidia(),
        "version_torch": torch.__version__,
        "version_transformers": transformers.__version__,
        "version_bitsandbytes": bitsandbytes.__version__,
        "version_sentence_transformers": sentence_transformers.__version__,
        "ram_systeme_go": obtenir_ram_systeme_go(),
        "cpu": obtenir_nom_cpu(),
        "taille_index_octets": os.path.getsize(os.path.join(args.index_dir, "index.faiss")),
        "nombre_documents": len(engine.manifest.get("pdf", [])),
        "nombre_passages": len(engine.chunks),
        "modele_embeddings": rag_engine.EMBEDDING_MODEL_NAME,
        "modele_llm": rag_engine.LLM_MODEL_NAME,
        "seed": args.seed,
        "repetitions": args.repetitions,
        "questions": QUESTIONS,
    }

    print("Measuring time to first token (dedicated call)...")
    premier_token = mesurer_premier_token(engine, QUESTIONS[0])

    print("Warming up (not counted)...")
    _, erreurs_echauffement = executer_un_appel(engine, torch, QUESTIONS[0])

    mesures_brutes = []
    erreurs: list[dict] = list(erreurs_echauffement)
    reponses_par_question: dict[str, list[dict]] = {}

    for question in QUESTIONS:
        reponses_par_question[question] = []
        for repetition in range(1, args.repetitions + 1):
            print(f"Question {QUESTIONS.index(question) + 1}/{len(QUESTIONS)}, repetition {repetition}/{args.repetitions}...")
            mesure, erreurs_appel = executer_un_appel(engine, torch, question)
            if mesure is None:
                erreurs.extend({**e, "question": question, "repetition": repetition} for e in erreurs_appel)
                continue
            mesure_complete = {"question": question, "repetition": repetition, **mesure}
            mesures_brutes.append(mesure_complete)
            reponses_par_question[question].append(mesure)

    # --- Global and per-question aggregates ---
    def valeurs(cle, sous_ensemble=None):
        source = sous_ensemble if sous_ensemble is not None else mesures_brutes
        return [m[cle] for m in source]

    agregats = {
        "global": {
            "temps_recherche_secondes": agreger(valeurs("temps_recherche_secondes")),
            "temps_generation_secondes": agreger(valeurs("temps_generation_secondes")),
            "temps_total_secondes": agreger(valeurs("temps_total_secondes")),
            "tokens_par_seconde": agreger(valeurs("tokens_par_seconde")),
        },
        "par_question": {
            question: {
                "temps_total_secondes": agreger(valeurs("temps_total_secondes", mesures)),
                "tokens_par_seconde": agreger(valeurs("tokens_par_seconde", mesures)),
                "statuts": [m["status"] for m in mesures],
            }
            for question, mesures in reponses_par_question.items()
        },
    }

    reponses = [
        {
            "question": question,
            "reponses": [m["answer"] for m in mesures],
            "statuts": [m["status"] for m in mesures],
        }
        for question, mesures in reponses_par_question.items()
    ]

    resultat_final = {
        "configuration": configuration,
        "temps_installation_secondes": temps_installation,
        "temps_chargement": {
            "index_secondes": engine.timings_chargement.get("index_secondes"),
            "embedder_secondes": engine.timings_chargement.get("embedder_secondes"),
            "llm_secondes": engine.timings_chargement.get("llm_secondes"),
        },
        "premier_appel_a_froid": {
            "erreurs": erreurs_echauffement,
        },
        "premier_token": premier_token,
        "memoire_gpu_avant_chargement_octets": memoire_gpu_avant_chargement,
        "memoire_gpu_apres_chargement_octets": memoire_gpu_apres_chargement,
        "mesures_brutes": mesures_brutes,
        "agregats": agregats,
        "reponses": reponses,
        "erreurs": erreurs,
        "avertissements": avertissements,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultat_final, f, ensure_ascii=False, indent=2, default=str)

    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
