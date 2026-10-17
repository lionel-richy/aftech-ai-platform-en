"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Settings2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

export type EtatIntegration = "non_connecte" | "configuration_requise" | "connecte" | "erreur";

const STYLES: Record<
  EtatIntegration,
  { labelKey: "statusNotConnected" | "statusConfigRequired" | "statusConnected" | "statusError"; classe: string; Icone: typeof XCircle }
> = {
  non_connecte: { labelKey: "statusNotConnected", classe: "text-[var(--text-muted)] bg-white/5 border-[var(--border)]", Icone: XCircle },
  configuration_requise: { labelKey: "statusConfigRequired", classe: "text-warning bg-[var(--warning-bg)] border-warning/30", Icone: Settings2 },
  connecte: { labelKey: "statusConnected", classe: "text-success bg-[var(--success-bg)] border-success/30", Icone: CheckCircle2 },
  erreur: { labelKey: "statusError", classe: "text-danger bg-[var(--danger-bg)] border-danger/30", Icone: AlertCircle },
};

export function IntegrationCard({
  nom,
  icone,
  etat,
  note,
}: {
  nom: string;
  /** Already-built element (e.g. <GitFork className="h-5 w-5" />), never
   * the component itself: a function can't cross the server -> client
   * boundary. */
  icone: ReactNode;
  etat: EtatIntegration;
  note?: string;
}) {
  const [ouvert, setOuvert] = useState(false);
  const t = useTranslations("Integrations");
  const { labelKey, classe, Icone: IconeEtat } = STYLES[etat];

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {icone}
          <span className="text-sm font-medium text-[var(--text-primary)]">{nom}</span>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${classe}`}>
          <IconeEtat aria-hidden className="h-3 w-3" />
          {t(labelKey)}
        </span>
      </div>

      {note && <p className="mt-2 text-xs text-[var(--text-secondary)]">{note}</p>}

      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        aria-expanded={ouvert}
        className="mt-3 text-xs font-medium text-primary hover:underline"
      >
        {ouvert ? t("hide") : t("configure")}
      </button>

      {ouvert && (
        <div role="note" className="mt-2 rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] p-3 text-xs text-[var(--text-secondary)]">
          {t("noSecretNote")}
        </div>
      )}
    </div>
  );
}
