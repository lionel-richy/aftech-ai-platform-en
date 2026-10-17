"use client";

import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";

import { definirLocale } from "@/lib/actions/locale";
import { LOCALES, type Locale } from "@/i18n/config";

const NOMS_LANGUE: Record<Locale, string> = {
  fr: "Français",
  en: "English",
  de: "Deutsch",
};

export function LocaleSwitcher() {
  const localeActuelle = useLocale() as Locale;
  const t = useTranslations("LanguageSwitcher");
  const [enCours, demarrerTransition] = useTransition();

  return (
    <label className="flex items-center gap-1.5 rounded-full border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)]">
      <Languages aria-hidden className="h-3.5 w-3.5 shrink-0" />
      <span className="sr-only">{t("label")}</span>
      <select
        aria-label={t("label")}
        value={localeActuelle}
        disabled={enCours}
        onChange={(evenement) => {
          const nouvelleLocale = evenement.target.value as Locale;
          demarrerTransition(() => {
            void definirLocale(nouvelleLocale);
          });
        }}
        className="bg-transparent text-[var(--text-primary)] focus:outline-none disabled:opacity-60"
      >
        {LOCALES.map((locale) => (
          <option key={locale} value={locale}>
            {NOMS_LANGUE[locale]}
          </option>
        ))}
      </select>
    </label>
  );
}
