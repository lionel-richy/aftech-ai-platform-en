import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { resoudreLocaleDepuisCookie } from "@/i18n/config";

// No URL-based routing (no /fr/..., /en/...): the language preference lives
// only in a non-sensitive cookie ("locale"), read here so that server AND
// client components get the right language from the very first render.
export default getRequestConfig(async () => {
  const store = await cookies();
  const locale = resoudreLocaleDepuisCookie(store.get("locale")?.value);

  const messages = (await import(`../messages/${locale}.json`)).default;

  return { locale, messages };
});
