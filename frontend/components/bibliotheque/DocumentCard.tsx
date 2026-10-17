"use client";

import { useState } from "react";
import { FileText, Layers, Loader2, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { LOCALE_BCP47, type Locale } from "@/i18n/config";
import { CLE_STATUT } from "@/lib/documentStatusLabels";
import type { DocumentItem } from "@/lib/types";

const STYLE_PAR_STATUT: Record<string, string> = {
  READY: "border-success/30 bg-[var(--success-bg)] text-success",
  UPLOADED: "border-[var(--border)] bg-white/5 text-[var(--text-muted)]",
  EXTRACTING: "border-warning/30 bg-[var(--warning-bg)] text-warning",
  INDEXING: "border-warning/30 bg-[var(--warning-bg)] text-warning",
  FAILED: "border-danger/30 bg-[var(--danger-bg)] text-danger",
  DELETING: "border-danger/30 bg-[var(--danger-bg)] text-danger",
};

export function DocumentCard({
  document,
  onSupprime,
}: {
  document: DocumentItem;
  onSupprime?: (id: string) => void;
}) {
  const locale = useLocale() as Locale;
  const t = useTranslations("Bibliotheque");
  const [confirmationOuverte, setConfirmationOuverte] = useState(false);
  const [suppressionEnCours, setSuppressionEnCours] = useState(false);
  const [erreurSuppression, setErreurSuppression] = useState<string | null>(null);

  const dateFormatee = document.date_index
    ? new Intl.DateTimeFormat(LOCALE_BCP47[locale], {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(new Date(document.date_index))
    : null;

  const statut = document.statut ?? "READY";
  const labelStatut =
    statut === "READY" ? t("indexedBadge") : t(CLE_STATUT[statut as keyof typeof CLE_STATUT] ?? "statusFailed");

  async function confirmerSuppression() {
    if (!document.id) return;
    setSuppressionEnCours(true);
    setErreurSuppression(null);
    try {
      const reponse = await fetch(`/api/documents/${document.id}`, { method: "DELETE" });
      if (!reponse.ok) {
        setErreurSuppression(t("deleteFailed"));
        setSuppressionEnCours(false);
        return;
      }
      onSupprime?.(document.id);
    } catch {
      setErreurSuppression(t("deleteFailed"));
      setSuppressionEnCours(false);
    }
  }

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-[var(--radius-md)] bg-primary/10 p-2 text-primary">
          <FileText aria-hidden className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]" title={document.nom_fichier}>
            {document.nom_fichier}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)]">
            <span className="inline-flex items-center gap-1">
              <Layers aria-hidden className="h-3 w-3" />
              {t("pagesPassages", { pages: document.pages, passages: document.passages })}
            </span>
            {dateFormatee && <span>{t("indexedOn", { date: dateFormatee })}</span>}
          </div>
          {statut === "FAILED" && document.message_erreur && (
            <p className="mt-1 text-xs text-danger">{document.message_erreur}</p>
          )}
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${STYLE_PAR_STATUT[statut] ?? STYLE_PAR_STATUT.READY}`}
        >
          {(statut === "EXTRACTING" || statut === "INDEXING") && (
            <Loader2 aria-hidden className="h-3 w-3 animate-spin motion-reduce:animate-none" />
          )}
          {labelStatut}
        </span>
      </div>
      <p className="mt-3 truncate text-xs text-[var(--text-muted)]" title={document.hash_sha256}>
        {t("engineHash", { engine: document.modele_embeddings, hash: document.hash_sha256.slice(0, 12) })}
      </p>

      {document.supprimable && document.id && (
        <div className="mt-3 border-t border-[var(--border)] pt-3">
          {!confirmationOuverte ? (
            <button
              type="button"
              onClick={() => setConfirmationOuverte(true)}
              className="flex items-center gap-1.5 text-xs font-medium text-danger hover:underline"
            >
              <Trash2 aria-hidden className="h-3.5 w-3.5" />
              {t("delete")}
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-[var(--text-secondary)]">{t("deleteConfirm")}</span>
              <button
                type="button"
                onClick={confirmerSuppression}
                disabled={suppressionEnCours}
                className="rounded-[var(--radius-md)] bg-danger px-2 py-1 font-medium text-white disabled:opacity-60"
              >
                {suppressionEnCours ? t("deleteInProgress") : t("deleteConfirmYes")}
              </button>
              <button
                type="button"
                onClick={() => setConfirmationOuverte(false)}
                disabled={suppressionEnCours}
                className="rounded-[var(--radius-md)] border border-[var(--border)] px-2 py-1 text-[var(--text-secondary)]"
              >
                {t("deleteConfirmNo")}
              </button>
            </div>
          )}
          {erreurSuppression && <p className="mt-1 text-danger">{erreurSuppression}</p>}
        </div>
      )}
    </div>
  );
}
