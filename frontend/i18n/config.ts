export const LOCALES = ["fr", "en", "de"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_PAR_DEFAUT: Locale = "en";

// Mapping to a full BCP 47 locale, for Intl.DateTimeFormat /
// Intl.NumberFormat (dates and numbers displayed according to the chosen language).
export const LOCALE_BCP47: Record<Locale, string> = {
  fr: "fr-FR",
  en: "en-US",
  de: "de-DE",
};

export function estLocaleValide(valeur: string): valeur is Locale {
  return (LOCALES as readonly string[]).includes(valeur);
}

// Pure function (no next/headers or next-intl/server import): directly
// testable without a Next.js context, and shared with i18n/request.ts
// (server-side reading of the "locale" cookie).
export function resoudreLocaleDepuisCookie(valeurCookie: string | undefined): Locale {
  if (valeurCookie !== undefined && estLocaleValide(valeurCookie)) return valeurCookie;
  return LOCALE_PAR_DEFAUT;
}
