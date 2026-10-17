"""
Builds results/benchmarks/gpu/comparison.csv and recommendation.md from the
T4.json / L4.json / A100.json files produced by gpu_benchmark.py.

Runs ENTIRELY locally (no GPU required): reads JSON files already
downloaded from Colab, never triggers any heavy computation.

Important: if a GPU hasn't been benchmarked, it's absent from the CSV
rather than shown with made-up values — and recommendation.md says so
explicitly ("Benchmark not run").
"""

import argparse
import csv
import json
import os
from pathlib import Path

GPU_CONNUS = ("T4", "L4", "A100")

# General guidance (NOT measured by this benchmark, clearly flagged as
# such) for categories outside what's tested here.
RECOMMANDATIONS_NON_MESUREES = {
    "Larger Qwen (e.g. 14B/32B)": (
        "Not measured in this benchmark (which only tests Qwen 4B). A "
        "14B-32B model in 4-bit typically needs 16-24 GB of VRAM: test on "
        "L4 (24 GB) or A100 (40/80 GB), not on T4 (16 GB, often too tight)."
    ),
    "Whisper (audio transcription)": (
        "Not measured in this benchmark. Whisper (even large-v3) fits "
        "comfortably on a T4: generally the cheapest choice for this "
        "use case, unless very high concurrent transcription throughput is needed."
    ),
    "OCR": (
        "Not measured in this benchmark. Most modern OCR engines "
        "(e.g. based on lightweight transformers) run comfortably on a T4."
    ),
    "Vision (image classification/detection)": (
        "Not measured in this benchmark. Strongly depends on the chosen "
        "model; a T4 or L4 is enough for most classic vision models."
    ),
    "Image generation": (
        "Not measured in this benchmark. Modern diffusion models clearly "
        "benefit from an L4 or A100 (higher VRAM and memory bandwidth); "
        "a T4 remains usable but slower."
    ),
}


def charger_resultats(dossier: Path) -> dict:
    resultats = {}
    for gpu in GPU_CONNUS:
        chemin = dossier / f"{gpu}.json"
        if chemin.is_file():
            with open(chemin, encoding="utf-8") as f:
                resultats[gpu] = json.load(f)
    return resultats


def extraire_ligne_csv(gpu: str, donnees: dict) -> dict:
    config = donnees.get("configuration", {})
    agregats_global = donnees.get("agregats", {}).get("global", {})

    def valeur_agregat(cle, sous_cle="moyenne"):
        agregat = agregats_global.get(cle)
        return agregat.get(sous_cle) if agregat else None

    mesures = donnees.get("mesures_brutes", [])
    pics_memoire = [m["memoire_gpu_pic_octets"] for m in mesures if m.get("memoire_gpu_pic_octets") is not None]

    return {
        "gpu": gpu,
        "gpu_obtenu": config.get("gpu_obtenu"),
        "vram_totale_go": round(config.get("vram_totale_octets", 0) / (1024**3), 2) if config.get("vram_totale_octets") else None,
        "nb_documents": config.get("nombre_documents"),
        "nb_passages": config.get("nombre_passages"),
        "temps_chargement_index_s": donnees.get("temps_chargement", {}).get("index_secondes"),
        "temps_chargement_bge_s": donnees.get("temps_chargement", {}).get("embedder_secondes"),
        "temps_chargement_qwen_s": donnees.get("temps_chargement", {}).get("llm_secondes"),
        "temps_premier_token_s": (donnees.get("premier_token") or {}).get("temps_premier_token_secondes"),
        "temps_recherche_moyen_s": valeur_agregat("temps_recherche_secondes"),
        "temps_generation_moyen_s": valeur_agregat("temps_generation_secondes"),
        "temps_total_moyen_s": valeur_agregat("temps_total_secondes"),
        "tokens_par_seconde_moyen": valeur_agregat("tokens_par_seconde"),
        "memoire_gpu_pic_go_max": round(max(pics_memoire) / (1024**3), 2) if pics_memoire else None,
        "nb_erreurs": len(donnees.get("erreurs", [])),
        "nb_reponses_complete": sum(1 for m in mesures if m.get("status") == "COMPLETE"),
        "nb_reponses_partial": sum(1 for m in mesures if m.get("status") == "PARTIAL"),
        "nb_reponses_not_found": sum(1 for m in mesures if m.get("status") == "NOT_FOUND"),
    }


def construire_csv(resultats: dict, chemin_sortie: Path) -> list[dict]:
    lignes = [extraire_ligne_csv(gpu, donnees) for gpu, donnees in resultats.items()]
    os.makedirs(chemin_sortie.parent, exist_ok=True)

    if not lignes:
        # No results: write a CSV with only the header, no made-up row.
        colonnes = [
            "gpu", "gpu_obtenu", "vram_totale_go", "nb_documents", "nb_passages",
            "temps_chargement_index_s", "temps_chargement_bge_s", "temps_chargement_qwen_s",
            "temps_premier_token_s", "temps_recherche_moyen_s", "temps_generation_moyen_s",
            "temps_total_moyen_s", "tokens_par_seconde_moyen", "memoire_gpu_pic_go_max",
            "nb_erreurs", "nb_reponses_complete", "nb_reponses_partial", "nb_reponses_not_found",
        ]
        with open(chemin_sortie, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=colonnes).writeheader()
        return []

    colonnes = list(lignes[0].keys())
    with open(chemin_sortie, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(lignes)

    return lignes


def charger_usage_colab(dossier: Path, gpu: str) -> tuple[str | None, str | None]:
    avant = dossier / f"{gpu}_usage_avant.txt"
    apres = dossier / f"{gpu}_usage_apres.txt"
    texte_avant = avant.read_text(encoding="utf-8") if avant.is_file() else None
    texte_apres = apres.read_text(encoding="utf-8") if apres.is_file() else None
    return texte_avant, texte_apres


def construire_recommendation_md(resultats: dict, lignes_csv: list[dict], dossier: Path) -> str:
    lignes_md = ["# GPU Recommendation — AFTECH AI Platform", ""]

    gpu_testes = list(resultats.keys())
    gpu_manquants = [g for g in GPU_CONNUS if g not in gpu_testes]

    if not gpu_testes:
        lignes_md.append("**Benchmark not run.** No T4.json / L4.json / A100.json file found.")
        lignes_md.append("")
        lignes_md.append("Run `./scripts/run_gpu_benchmark.sh <T4|L4|A100>` then run this script again.")
        return "\n".join(lignes_md)

    if gpu_manquants:
        lignes_md.append(f"⚠️ GPUs not tested (absent from the comparison): {', '.join(gpu_manquants)}.")
        lignes_md.append("")

    lignes_md.append("## Measured in this benchmark")
    lignes_md.append("")

    ligne_par_gpu = {l["gpu"]: l for l in lignes_csv}

    lignes_md.append("### Qwen/Qwen3-4B-Instruct-2507 (4-bit)")
    for gpu in gpu_testes:
        l = ligne_par_gpu[gpu]
        lignes_md.append(
            f"- **{gpu}** ({l['gpu_obtenu']}): {l['tokens_par_seconde_moyen']:.1f} tokens/s on average, "
            f"{l['temps_total_moyen_s']:.2f} s/response on average, peak memory {l['memoire_gpu_pic_go_max']} GB "
            f"(out of {l['vram_totale_go']} GB available), {l['nb_erreurs']} error(s)."
            if l["tokens_par_seconde_moyen"] is not None
            else f"- **{gpu}**: incomplete data (see {gpu}.json)."
        )
    if gpu_testes:
        plus_rapide = max(
            (l for l in lignes_csv if l["tokens_par_seconde_moyen"] is not None),
            key=lambda l: l["tokens_par_seconde_moyen"],
            default=None,
        )
        if plus_rapide:
            lignes_md.append("")
            lignes_md.append(
                f"→ **Qwen 4B** recommendation: {plus_rapide['gpu']} is the fastest measured "
                f"({plus_rapide['tokens_par_seconde_moyen']:.1f} tokens/s). If budget is tight and the "
                "latency measured on T4 remains acceptable for the intended use, T4 stays the cheapest choice."
            )
    lignes_md.append("")

    lignes_md.append("### Embeddings (BAAI/bge-m3)")
    lignes_md.append(
        "- Computed on CPU in this pipeline (see `temps_chargement_bge_s` in comparison.csv): "
        "no GPU is needed for embeddings as used here."
    )
    lignes_md.append("")

    lignes_md.append("### Day-to-day development")
    lignes_md.append(
        "- The cheapest tested GPU that remains functional (0 CUDA/memory errors) is recommended "
        "for iterating during development — see the `nb_erreurs` column in comparison.csv."
    )
    lignes_md.append("")

    lignes_md.append("### Multi-user demo")
    lignes_md.append(
        "- This benchmark runs requests sequentially (no simulated concurrent load): "
        "no multi-user capacity recommendation can be drawn from these numbers alone. "
        "A dedicated concurrent load test would be needed before any recommendation here."
    )
    lignes_md.append("")

    lignes_md.append("## Not measured in this benchmark (general guidance)")
    lignes_md.append("")
    for categorie, texte in RECOMMANDATIONS_NON_MESUREES.items():
        lignes_md.append(f"### {categorie}")
        lignes_md.append(f"- {texte}")
        lignes_md.append("")

    lignes_md.append("## Colab usage (CCU)")
    lignes_md.append("")
    au_moins_une_mesure = False
    for gpu in gpu_testes:
        avant, apres = charger_usage_colab(dossier, gpu)
        if avant or apres:
            au_moins_une_mesure = True
            lignes_md.append(f"### {gpu}")
            lignes_md.append("```")
            lignes_md.append(f"Before: {avant.strip() if avant else 'not captured'}")
            lignes_md.append(f"After: {apres.strip() if apres else 'not captured'}")
            lignes_md.append("```")
            lignes_md.append("")
    if not au_moins_une_mesure:
        lignes_md.append(
            "Not measured automatically (`<GPU>_usage_avant.txt` / `<GPU>_usage_apres.txt` files absent). "
            "If `colab usage` wasn't available locally during the run, copy its output "
            "manually before/after the next benchmark — **we do not make up** compute units consumed here."
        )

    return "\n".join(lignes_md)


def main():
    parser = argparse.ArgumentParser(description="Builds comparison.csv and recommendation.md from the GPU benchmark JSON files.")
    parser.add_argument("--dossier", default="results/benchmarks/gpu", help="Folder containing T4.json/L4.json/A100.json")
    args = parser.parse_args()

    dossier = Path(args.dossier)
    resultats = charger_resultats(dossier)

    lignes_csv = construire_csv(resultats, dossier / "comparison.csv")
    print(f"comparison.csv written ({len(lignes_csv)} row(s)) to {dossier / 'comparison.csv'}")

    contenu_md = construire_recommendation_md(resultats, lignes_csv, dossier)
    chemin_md = dossier / "recommendation.md"
    os.makedirs(chemin_md.parent, exist_ok=True)
    chemin_md.write_text(contenu_md, encoding="utf-8")
    print(f"recommendation.md written to {chemin_md}")


if __name__ == "__main__":
    main()
