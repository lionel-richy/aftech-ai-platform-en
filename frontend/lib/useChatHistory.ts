"use client";

import { useCallback, useEffect, useState } from "react";

import type { ErreurExplicationCles } from "./errorMessages";
import type { AskResponse } from "./types";

export interface ChatTurn {
  id: string;
  question: string;
  reponse?: AskResponse;
  // Translation keys (namespace "Errors"), not resolved text: lets the
  // history stay correct even after a language change.
  erreur?: ErreurExplicationCles;
  enCours?: boolean;
}

const CLE_LOCALSTORAGE = "aftech.assistant.historique";

function litHistoriqueLocal(): ChatTurn[] {
  try {
    const brut = window.localStorage.getItem(CLE_LOCALSTORAGE);
    if (!brut) return [];
    const valeur = JSON.parse(brut);
    return Array.isArray(valeur) ? valeur : [];
  } catch {
    return [];
  }
}

// History LOCAL to the browser session only (requirement: "don't make up a
// server-side conversational memory that doesn't exist yet" — the backend
// knows nothing about this history).
export function useChatHistory() {
  const [tours, setTours] = useState<ChatTurn[]>([]);
  const [hydrate, setHydrate] = useState(false);

  useEffect(() => {
    // One-time read of an external system (localStorage, inaccessible to
    // server rendering) after mount: a case explicitly justifying this rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTours(litHistoriqueLocal());
    setHydrate(true);
  }, []);

  useEffect(() => {
    if (!hydrate) return;
    try {
      window.localStorage.setItem(CLE_LOCALSTORAGE, JSON.stringify(tours));
    } catch {
      // Storage unavailable: the history stays functional for the current session.
    }
  }, [tours, hydrate]);

  const ajouter = useCallback((tour: ChatTurn) => {
    setTours((precedents) => [...precedents, tour]);
  }, []);

  const mettreAJour = useCallback((id: string, patch: Partial<ChatTurn>) => {
    setTours((precedents) => precedents.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  const nouvelleConversation = useCallback(() => {
    setTours([]);
    try {
      window.localStorage.removeItem(CLE_LOCALSTORAGE);
    } catch {
      // Nothing serious if the storage can't be cleared.
    }
  }, []);

  return { tours, ajouter, mettreAJour, nouvelleConversation, hydrate };
}
