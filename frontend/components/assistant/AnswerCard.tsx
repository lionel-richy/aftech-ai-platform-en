"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import { useTranslations } from "next-intl";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { EXPLICATION_STATUT_KEYS } from "@/lib/errorMessages";
import type { AskResponse } from "@/lib/types";
import { SourceCard } from "./SourceCard";

export function AnswerCard({ reponse }: { reponse: AskResponse }) {
  const [detailsOuverts, setDetailsOuverts] = useState(false);
  const [copie, setCopie] = useState(false);
  const t = useTranslations("Assistant");
  const tCommon = useTranslations("Common");

  const copier = async () => {
    try {
      await navigator.clipboard.writeText(reponse.answer);
      setCopie(true);
      setTimeout(() => setCopie(false), 2000);
    } catch {
      // Clipboard unavailable (browser permissions): silently ignored.
    }
  };

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between gap-2">
        <StatusBadge status={reponse.status} />
        <button
          type="button"
          onClick={copier}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]"
        >
          {copie ? <Check aria-hidden className="h-3.5 w-3.5" /> : <Copy aria-hidden className="h-3.5 w-3.5" />}
          {copie ? t("copie") : t("copier")}
        </button>
      </div>

      <p className="mt-1 text-xs text-[var(--text-secondary)]">{tCommon(EXPLICATION_STATUT_KEYS[reponse.status])}</p>

      <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-[var(--text-primary)]">
        {reponse.answer}
      </p>

      {reponse.sources.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">{t("sourcesTitle")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {reponse.sources.map((source, index) => (
              <SourceCard key={`${source.fichier}-${source.page}-${index}`} source={source} afficherScore={detailsOuverts} />
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setDetailsOuverts((v) => !v)}
        aria-expanded={detailsOuverts}
        className="mt-4 flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
      >
        {detailsOuverts ? <ChevronUp aria-hidden className="h-3.5 w-3.5" /> : <ChevronDown aria-hidden className="h-3.5 w-3.5" />}
        {tCommon("detailsTechniques")}
      </button>

      {detailsOuverts && (
        <dl className="mt-3 grid grid-cols-3 gap-3 rounded-[var(--radius-md)] bg-[var(--surface-elevated)] p-3 text-xs">
          <div>
            <dt className="text-[var(--text-muted)]">{t("detailsRecherche")}</dt>
            <dd className="text-[var(--text-primary)]">{reponse.timings.recherche_secondes.toFixed(2)} s</dd>
          </div>
          <div>
            <dt className="text-[var(--text-muted)]">{t("detailsGeneration")}</dt>
            <dd className="text-[var(--text-primary)]">{reponse.timings.generation_secondes.toFixed(2)} s</dd>
          </div>
          <div>
            <dt className="text-[var(--text-muted)]">{t("detailsTotal")}</dt>
            <dd className="text-[var(--text-primary)]">{reponse.timings.total_secondes.toFixed(2)} s</dd>
          </div>
          <div className="col-span-3">
            <dt className="text-[var(--text-muted)]">{tCommon("requestId")}</dt>
            <dd className="truncate font-mono text-[var(--text-primary)]" title={reponse.request_id}>
              {reponse.request_id}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}
