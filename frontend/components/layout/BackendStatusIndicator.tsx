"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useEtatMoteur } from "@/lib/engineStatus";

// IMPORTANT: this component runs PERMANENTLY (every page, every 30s, as
// long as the tab is open). It NEVER calls /api/health or /api/ask (GPU
// routes) — only /api/availability (CPU-only, separate Modal function, see
// backend/app/modal_app.py). Otherwise this automatic ping would
// indefinitely prevent the GPU's scale-to-zero (that's the bug fixed here).
// The ENGINE's detailed state (starting/ready/unavailable) comes only from
// real interactions (lib/engineStatus.ts), never from this ping.
type EtatApi = "verification" | "disponible" | "indisponible";

export function BackendStatusIndicator({ compact = false }: { compact?: boolean }) {
  const [etatApi, setEtatApi] = useState<EtatApi>("verification");
  const etatMoteur = useEtatMoteur();
  const t = useTranslations("BackendStatus");

  useEffect(() => {
    let annule = false;

    async function verifier() {
      try {
        const reponse = await fetch("/api/availability", { cache: "no-store" });
        if (!annule) setEtatApi(reponse.ok ? "disponible" : "indisponible");
      } catch {
        if (!annule) setEtatApi("indisponible");
      }
    }

    verifier();
    const intervalle = setInterval(verifier, 30000);
    return () => {
      annule = true;
      clearInterval(intervalle);
    };
  }, []);

  const { couleur, label } = (() => {
    if (etatApi === "verification") return { couleur: "bg-[var(--text-muted)]", label: t("checking") };
    if (etatApi === "indisponible") return { couleur: "bg-danger", label: t("apiUnreachable") };

    // API available: the detail shown depends on the ENGINE's state, known
    // only through real interactions (never this automatic ping).
    switch (etatMoteur.etat) {
      case "demarrage":
        return { couleur: "bg-warning", label: t("engineStarting") };
      case "pret":
        return { couleur: "bg-success", label: t("engineReady") };
      case "indisponible":
        return { couleur: "bg-danger", label: t("engineUnavailable") };
      case "veille":
      default:
        return { couleur: "bg-[var(--text-muted)]", label: t("engineIdle") };
    }
  })();

  return (
    <div
      role="status"
      aria-label={label}
      title={label}
      className="flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1.5 text-xs text-[var(--text-secondary)]"
    >
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${couleur}`} />
      {!compact && <span>{label}</span>}
    </div>
  );
}
