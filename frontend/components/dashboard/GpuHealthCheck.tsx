"use client";

import { useState } from "react";
import { Activity, Cpu, Database, FileStack, Gauge, Layers, RefreshCw, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { StatTile } from "@/components/ui/StatTile";
import { definirEtatMoteur } from "@/lib/engineStatus";
import { LOCALE_BCP47, type Locale } from "@/i18n/config";
import type { HealthResponse } from "@/lib/types";

function formaterGo(octets: number): string {
  return (octets / 1024 ** 3).toFixed(2);
}

// Requirement: "the detailed GPU check must only be triggered by a real
// question, or MANUALLY from the dashboard" — this component is therefore
// client-side, triggered by a click, NEVER by a page load or an automatic
// loop. This is the only way (along with ChatView) to call /api/health
// (a GPU route).
export function GpuHealthCheck() {
  const [etat, setEtat] = useState<"non_verifie" | "verification" | "pret" | "indisponible">("non_verifie");
  const [sante, setSante] = useState<HealthResponse | null>(null);
  const locale = useLocale() as Locale;
  const t = useTranslations("Dashboard");
  const nombres = new Intl.NumberFormat(LOCALE_BCP47[locale]);

  async function verifier() {
    setEtat("verification");
    definirEtatMoteur({ etat: "demarrage", vramUtiliseeOctets: null, vramTotaleOctets: null });
    try {
      const reponse = await fetch("/api/health", { cache: "no-store" });
      if (!reponse.ok) {
        setEtat("indisponible");
        definirEtatMoteur({ etat: "indisponible", vramUtiliseeOctets: null, vramTotaleOctets: null });
        return;
      }
      const donnees: HealthResponse = await reponse.json();
      setSante(donnees);
      setEtat("pret");
      definirEtatMoteur({
        etat: "pret",
        vramUtiliseeOctets: donnees.vram_utilisee_octets,
        vramTotaleOctets: donnees.vram_totale_octets,
      });
    } catch {
      setEtat("indisponible");
      definirEtatMoteur({ etat: "indisponible", vramUtiliseeOctets: null, vramTotaleOctets: null });
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--text-secondary)]">{t("gpuCheckExplanation")}</p>
        <button
          type="button"
          onClick={verifier}
          disabled={etat === "verification"}
          className="flex shrink-0 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)] disabled:opacity-60"
        >
          <RefreshCw aria-hidden className={`h-3.5 w-3.5 ${etat === "verification" ? "animate-spin motion-reduce:animate-none" : ""}`} />
          {etat === "verification" ? t("gpuCheckInProgress") : t("gpuCheckButton")}
        </button>
      </div>

      {etat === "indisponible" && (
        <p className="text-xs text-danger">{t("gpuCheckUnavailable")}</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label={t("statBackend")}
          value={sante ? (sante.ready ? t("statOperational") : t("statDegraded")) : null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<Activity className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statDocuments")}
          value={sante ? nombres.format(sante.documents_count) : null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<FileStack className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statPassagesIndexed")}
          value={sante ? nombres.format(sante.chunks_count) : null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<Layers className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statGpuActive")}
          value={sante?.gpu ?? null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<Cpu className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statLlmModel")}
          value={sante?.llm_model ?? null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<Sparkles className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statEmbeddingModel")}
          value={sante?.embedding_model ?? null}
          unavailableReason={!sante ? t("gpuCheckNotYetRun") : undefined}
          icon={<Database className="h-4 w-4" aria-hidden />}
        />
        <StatTile
          label={t("statGpuMemory")}
          value={
            sante?.vram_utilisee_octets != null && sante?.vram_totale_octets != null
              ? `${formaterGo(sante.vram_utilisee_octets)} / ${formaterGo(sante.vram_totale_octets)} GB`
              : null
          }
          unavailableReason={
            !sante
              ? t("gpuCheckNotYetRun")
              : sante.vram_totale_octets == null
                ? t("statGpuMemoryUnavailable")
                : undefined
          }
          icon={<Gauge className="h-4 w-4" aria-hidden />}
        />
      </div>
    </div>
  );
}
