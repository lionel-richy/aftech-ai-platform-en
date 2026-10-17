"use client";

import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";

import type { SourceItem } from "@/lib/types";

// source.fichier and source.extrait are rendered as-is, in the ORIGINAL
// language of the source document: never run them through t() (requirement:
// exact citations must never be translated).
export function SourceCard({ source, afficherScore }: { source: SourceItem; afficherScore: boolean }) {
  const t = useTranslations("Assistant");

  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
          <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate" title={source.fichier}>
            {source.fichier}
          </span>
        </div>
        <span className="shrink-0 text-xs text-[var(--text-muted)]">{t("sourcePage", { page: source.page })}</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{source.extrait}</p>
      {afficherScore && (
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {t("semanticScore", { score: source.score.toFixed(3) })}
        </p>
      )}
    </div>
  );
}
