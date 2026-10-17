"use client";

import { useEffect, useState } from "react";

// SHARED state (within the browser tab) of the AI engine (Qwen + BGE-M3 on
// Modal GPU) — updated ONLY by real interactions (a question sent to
// /api/ask, or a manual GPU check from the dashboard). NEVER by automatic
// monitoring: that's the whole point of separating this state from
// BackendStatusIndicator's periodic ping (see lib/availability.ts), which
// must NEVER call a GPU route.
//
// Module singleton (no React context): simple, no new dependency, and
// deliberately reset to "idle" on every page reload (no "GPU ready"
// information should survive a reload: we no longer KNOW whether the
// container is still warm).

export type EtatMoteur = "veille" | "demarrage" | "pret" | "indisponible";

export interface EtatMoteurSnapshot {
  etat: EtatMoteur;
  // null if unknown or if the engine is idle — never a made-up value
  // (requirement: never display a fake GPU memory reading).
  vramUtiliseeOctets: number | null;
  vramTotaleOctets: number | null;
}

const ETAT_INITIAL: EtatMoteurSnapshot = {
  etat: "veille",
  vramUtiliseeOctets: null,
  vramTotaleOctets: null,
};

let etatActuel: EtatMoteurSnapshot = ETAT_INITIAL;
const abonnes = new Set<(etat: EtatMoteurSnapshot) => void>();

export function definirEtatMoteur(etat: EtatMoteurSnapshot): void {
  etatActuel = etat;
  for (const f of abonnes) f(etatActuel);
}

export function etatMoteurActuel(): EtatMoteurSnapshot {
  return etatActuel;
}

export function sabonnerEtatMoteur(f: (etat: EtatMoteurSnapshot) => void): () => void {
  abonnes.add(f);
  return () => abonnes.delete(f);
}

// Tests only: resets the singleton to its initial state, otherwise test
// file execution order would contaminate each other.
export function reinitialiserEtatMoteurPourLesTests(): void {
  etatActuel = ETAT_INITIAL;
}

export function useEtatMoteur(): EtatMoteurSnapshot {
  const [etat, setEtat] = useState(etatMoteurActuel);
  useEffect(() => sabonnerEtatMoteur(setEtat), []);
  return etat;
}
