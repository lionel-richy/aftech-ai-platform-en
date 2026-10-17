"use client";

import { useRef, useState } from "react";
import type { DragEvent } from "react";
import { Loader2, Plus, UploadCloud } from "lucide-react";
import { useTranslations } from "next-intl";

import { CLE_STATUT } from "@/lib/documentStatusLabels";
import { expliquerErreurHttp, type ErreurExplicationCles } from "@/lib/errorMessages";
import type { DocumentStatusResponse, DocumentUploadResponse } from "@/lib/types";

const INTERVALLE_SONDAGE_MS = 1500;
const STATUTS_TERMINAUX = new Set(["READY", "FAILED"]);

async function attendreStatutFinal(id: string): Promise<DocumentStatusResponse | null> {
  // Simple polling (no WebSocket): enough for processing that takes a few
  // seconds to a few minutes (see GpuHealthCheck.tsx for the same
  // principle on the dashboard side).
  while (true) {
    const reponse = await fetch(`/api/documents/${id}/status`, { cache: "no-store" });
    if (!reponse.ok) return null;
    const statut: DocumentStatusResponse = await reponse.json();
    if (STATUTS_TERMINAUX.has(statut.statut)) return statut;
    await new Promise((resolve) => setTimeout(resolve, INTERVALLE_SONDAGE_MS));
  }
}

export function AjouterDocumentButton({ onDocumentAjoute }: { onDocumentAjoute?: () => void }) {
  const [ouvert, setOuvert] = useState(false);
  const [survole, setSurvole] = useState(false);
  const [etat, setEtat] = useState<"inactif" | "envoi" | "traitement">("inactif");
  const [statutCourant, setStatutCourant] = useState<string | null>(null);
  const [erreur, setErreur] = useState<ErreurExplicationCles | null>(null);
  const t = useTranslations("Bibliotheque");
  const tErrors = useTranslations("Errors");
  const refInput = useRef<HTMLInputElement>(null);

  async function envoyerFichier(fichier: File) {
    setErreur(null);
    setEtat("envoi");

    const formulaire = new FormData();
    formulaire.append("fichier", fichier);

    try {
      const reponse = await fetch("/api/documents", { method: "POST", body: formulaire });
      const corps = await reponse.json().catch(() => null);

      if (!reponse.ok) {
        setErreur(expliquerErreurHttp(reponse.status, corps?.message, corps?.code, corps?.values));
        setEtat("inactif");
        return;
      }

      const upload: DocumentUploadResponse = corps;
      setEtat("traitement");
      setStatutCourant(upload.statut);

      const final = await attendreStatutFinal(upload.id);
      setEtat("inactif");
      setStatutCourant(null);

      if (final?.statut === "FAILED") {
        setErreur({
          titreKey: "validationTitle",
          descriptionKey: "validationDefault",
          descriptionOverride: final.message_erreur ?? undefined,
          type: "erreur",
        });
        return;
      }

      onDocumentAjoute?.();
    } catch {
      setErreur({ titreKey: "unavailableTitle", descriptionKey: "unavailableDefault", type: "indisponible" });
      setEtat("inactif");
    }
  }

  function gererDepot(evenement: DragEvent<HTMLDivElement>) {
    evenement.preventDefault();
    setSurvole(false);
    const fichier = evenement.dataTransfer.files?.[0];
    if (fichier) void envoyerFichier(fichier);
  }

  const enCours = etat !== "inactif";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        aria-expanded={ouvert}
        className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        <Plus aria-hidden className="h-3.5 w-3.5" />
        {t("addDocument")}
      </button>

      {ouvert && (
        <div
          role="dialog"
          aria-label={t("addDocument")}
          className="absolute right-0 top-full z-10 mt-2 w-80 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)] shadow-lg"
        >
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setSurvole(true);
            }}
            onDragLeave={() => setSurvole(false)}
            onDrop={gererDepot}
            onClick={() => !enCours && refInput.current?.click()}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !enCours) refInput.current?.click();
            }}
            role="button"
            tabIndex={0}
            aria-label={t("dropzoneLabel")}
            aria-busy={enCours}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-[var(--radius-md)] border-2 border-dashed p-4 text-center transition-colors ${
              survole ? "border-primary bg-primary/5" : "border-[var(--border-strong)]"
            } ${enCours ? "cursor-not-allowed opacity-70" : ""}`}
          >
            {enCours ? (
              <Loader2 aria-hidden className="h-6 w-6 animate-spin text-primary motion-reduce:animate-none" />
            ) : (
              <UploadCloud aria-hidden className="h-6 w-6 text-[var(--text-muted)]" />
            )}
            <p>
              {etat === "envoi" && t("uploadInProgress")}
              {etat === "traitement" &&
                t(CLE_STATUT[(statutCourant ?? "EXTRACTING") as keyof typeof CLE_STATUT] ?? "statusExtracting")}
              {etat === "inactif" && t("dropzoneLabel")}
            </p>
            <input
              ref={refInput}
              type="file"
              accept="application/pdf"
              aria-label={t("dropzoneLabel")}
              className="sr-only"
              disabled={enCours}
              onChange={(e) => {
                const fichier = e.target.files?.[0];
                if (fichier) void envoyerFichier(fichier);
                e.target.value = "";
              }}
            />
          </div>

          {erreur && (
            <p className="mt-2 text-danger">{erreur.descriptionOverride ?? tErrors(erreur.descriptionKey, erreur.descriptionValues)}</p>
          )}

          <p className="mt-2 text-[var(--text-muted)]">{t("addDocumentNote")}</p>
        </div>
      )}
    </div>
  );
}
