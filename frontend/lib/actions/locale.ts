"use server";

import { cookies } from "next/headers";

import { estLocaleValide, type Locale } from "@/i18n/config";

// Non-sensitive cookie (no user data): only stores the interface's language
// preference. Calling this action from the client automatically triggers a
// re-render of the server components with the new language — no manual
// router.refresh() needed.
export async function definirLocale(locale: Locale) {
  if (!estLocaleValide(locale)) return;
  const store = await cookies();
  store.set("locale", locale, { maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
}
