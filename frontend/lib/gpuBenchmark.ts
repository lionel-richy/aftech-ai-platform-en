import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

export interface LigneComparisonGpu {
  gpu: string;
  gpu_obtenu: string;
  vram_totale_go: number | null;
  tokens_par_seconde_moyen: number | null;
  temps_total_moyen_s: number | null;
  memoire_gpu_pic_go_max: number | null;
  nb_erreurs: number | null;
}

export interface ComparisonGpu {
  executed: boolean;
  lignes: LigneComparisonGpu[];
}

const COLONNES_NUMERIQUES = [
  "vram_totale_go",
  "tokens_par_seconde_moyen",
  "temps_total_moyen_s",
  "memoire_gpu_pic_go_max",
  "nb_erreurs",
] as const;

// Never a made-up value: if comparison.csv doesn't exist yet (no real
// benchmark has run), we say so explicitly instead of fabricating numbers.
// Reads the output of scripts/build_gpu_comparison.py (produced on the Mac
// after downloading the results from Colab), never recomputed here.
export async function lireComparisonGpu(): Promise<ComparisonGpu> {
  const chemin = path.join(process.cwd(), "..", "results", "benchmarks", "gpu", "comparison.csv");

  let contenu: string;
  try {
    contenu = await readFile(chemin, "utf-8");
  } catch {
    return { executed: false, lignes: [] };
  }

  const [enteteLigne, ...lignesBrutes] = contenu.trim().split("\n");
  const entetes = enteteLigne.split(",");
  const lignesDonnees = lignesBrutes.filter((l) => l.trim().length > 0);

  if (lignesDonnees.length === 0) {
    return { executed: false, lignes: [] };
  }

  const nombre = (valeur: string | undefined): number | null => {
    if (valeur === undefined || valeur === "") return null;
    const n = Number(valeur);
    return Number.isFinite(n) ? n : null;
  };

  const lignes: LigneComparisonGpu[] = lignesDonnees.map((ligne) => {
    const valeurs = ligne.split(",");
    const parColonne: Record<string, string> = {};
    entetes.forEach((cle, index) => {
      parColonne[cle] = valeurs[index];
    });

    const ligneTypee = {
      gpu: parColonne.gpu ?? "?",
      gpu_obtenu: parColonne.gpu_obtenu ?? "",
    } as LigneComparisonGpu;

    for (const colonne of COLONNES_NUMERIQUES) {
      ligneTypee[colonne] = nombre(parColonne[colonne]);
    }

    return ligneTypee;
  });

  return { executed: true, lignes };
}
