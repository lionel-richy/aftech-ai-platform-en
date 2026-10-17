// Render wrapper shared by component tests: provides the next-intl context
// (useTranslations/useLocale throw without it). The real messages from
// messages/{locale}.json are used directly — a single source of truth,
// tests never duplicate the translations. Default locale here is "fr" as a
// test-only convenience (unrelated to the app's runtime default locale, see
// i18n/config.ts's LOCALE_PAR_DEFAUT).
import type { ReactElement, ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Locale } from "@/i18n/config";
import fr from "@/messages/fr.json";
import en from "@/messages/en.json";
import de from "@/messages/de.json";

const MESSAGES_PAR_LOCALE: Record<Locale, typeof fr> = { fr, en, de };

export function renderAvecIntl(
  ui: ReactElement,
  { locale = "fr" as Locale, ...options }: { locale?: Locale } & Omit<RenderOptions, "wrapper"> = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES_PAR_LOCALE[locale]}>
        {children}
      </NextIntlClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}
