"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Loader2, Plus, Send } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { BackendUnavailableState, ErrorState } from "@/components/ui/StateViews";
import { definirEtatMoteur } from "@/lib/engineStatus";
import { expliquerErreurHttp } from "@/lib/errorMessages";
import type { AskResponse } from "@/lib/types";
import { useChatHistory } from "@/lib/useChatHistory";
import type { Locale } from "@/i18n/config";
import { AnswerCard } from "./AnswerCard";

export function ChatView() {
  const { tours, ajouter, mettreAJour, nouvelleConversation, hydrate } = useChatHistory();
  const [saisie, setSaisie] = useState("");
  const [envoiEnCours, setEnvoiEnCours] = useState(false);
  const refTextarea = useRef<HTMLTextAreaElement>(null);
  const t = useTranslations("Assistant");
  const tErrors = useTranslations("Errors");
  const locale = useLocale() as Locale;

  const QUESTIONS_EXEMPLES = [t("exampleQuestion1"), t("exampleQuestion2"), t("exampleQuestion3")];

  async function envoyer(question: string) {
    const texte = question.trim();
    if (!texte || envoiEnCours) return;

    const id = crypto.randomUUID();
    ajouter({ id, question: texte, enCours: true });
    setSaisie("");
    setEnvoiEnCours(true);
    // A real question actually starts the engine (which is why this is the
    // ONLY action — along with the dashboard's manual check — allowed to
    // publish this state).
    definirEtatMoteur({ etat: "demarrage", vramUtiliseeOctets: null, vramTotaleOctets: null });

    try {
      const reponseHttp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // response_language: the backend must answer in the interface's
        // language, even if the source document is in a different one.
        body: JSON.stringify({ question: texte, top_k: 8, response_language: locale }),
      });

      if (!reponseHttp.ok) {
        const corps = await reponseHttp.json().catch(() => null);
        const explication = expliquerErreurHttp(reponseHttp.status, corps?.message, corps?.code, corps?.values);
        mettreAJour(id, { enCours: false, erreur: explication });
        definirEtatMoteur({
          etat: explication.type === "indisponible" ? "indisponible" : "pret",
          vramUtiliseeOctets: null,
          vramTotaleOctets: null,
        });
        return;
      }

      const reponse: AskResponse = await reponseHttp.json();
      mettreAJour(id, { enCours: false, reponse });
      definirEtatMoteur({ etat: "pret", vramUtiliseeOctets: null, vramTotaleOctets: null });
    } catch {
      mettreAJour(id, {
        enCours: false,
        erreur: {
          titreKey: "unavailableTitle",
          descriptionKey: "unavailableDefault",
          descriptionOverride: t("unreachableServer"),
          type: "indisponible",
        },
      });
      definirEtatMoteur({ etat: "indisponible", vramUtiliseeOctets: null, vramTotaleOctets: null });
    } finally {
      setEnvoiEnCours(false);
    }
  }

  function gererTouche(evenement: KeyboardEvent<HTMLTextAreaElement>) {
    if (evenement.key === "Enter" && !evenement.shiftKey) {
      evenement.preventDefault();
      envoyer(saisie);
    }
    // Shift+Enter: default textarea behavior (new line).
  }

  const backendIndisponible = tours.some((tour) => tour.erreur?.type === "indisponible");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end border-b border-[var(--border)] px-4 py-2 md:px-6">
        <button
          type="button"
          onClick={nouvelleConversation}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]"
        >
          <Plus aria-hidden className="h-3.5 w-3.5" />
          {t("newConversation")}
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6 md:px-6">
        {hydrate && tours.length === 0 && (
          <div className="mx-auto max-w-lg space-y-3 pt-8 text-center">
            <p className="text-sm text-[var(--text-secondary)]">{t("examplesIntro")}</p>
            <div className="flex flex-col gap-2">
              {QUESTIONS_EXEMPLES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => envoyer(q)}
                  className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-left text-sm text-[var(--text-secondary)] hover:border-primary/40 hover:text-[var(--text-primary)]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {tours.map((tour) => (
          <div key={tour.id} className="space-y-2">
            <div className="ml-auto max-w-[80%] rounded-[var(--radius-lg)] bg-primary/10 px-4 py-2.5 text-sm text-[var(--text-primary)]">
              {tour.question}
            </div>

            {tour.enCours && (
              <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <Loader2 aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" />
                {t("coldStartMessage")}
              </div>
            )}

            {tour.erreur && !tour.enCours && tour.erreur.type === "indisponible" && (
              <BackendUnavailableState
                description={
                  tour.erreur.descriptionOverride ?? tErrors(tour.erreur.descriptionKey, tour.erreur.descriptionValues)
                }
              />
            )}
            {tour.erreur && !tour.enCours && tour.erreur.type === "erreur" && (
              <ErrorState
                title={tErrors(tour.erreur.titreKey, tour.erreur.titreValues)}
                description={
                  tour.erreur.descriptionOverride ?? tErrors(tour.erreur.descriptionKey, tour.erreur.descriptionValues)
                }
              />
            )}

            {tour.reponse && !tour.enCours && <AnswerCard reponse={tour.reponse} />}
          </div>
        ))}
      </div>

      <div className="border-t border-[var(--border)] p-4 md:p-6">
        {backendIndisponible && (
          <p className="mb-2 text-xs text-warning">{t("backendSeemsUnavailable")}</p>
        )}
        <div className="flex items-end gap-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-2">
          <label htmlFor="assistant-saisie" className="sr-only">
            {t("questionLabel")}
          </label>
          <textarea
            id="assistant-saisie"
            ref={refTextarea}
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={gererTouche}
            placeholder={t("placeholder")}
            rows={1}
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => envoyer(saisie)}
            disabled={envoiEnCours || !saisie.trim()}
            aria-label={t("sendAriaLabel")}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-primary text-[var(--bg)] transition-opacity disabled:opacity-40"
          >
            <Send aria-hidden className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
