// End-to-end proof: a PROXY error (code="question_too_long",
// "backend_unreachable", etc.) actually renders translated in all 3
// languages, not just "the right key is chosen" (already covered in
// errorMessages.test.ts).
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useTranslations } from "next-intl";

import { expliquerErreurHttp } from "@/lib/errorMessages";
import type { Locale } from "@/i18n/config";
import { renderAvecIntl } from "./test-utils";

function ErreurRendue({ status, code, values }: { status: number; code: Parameters<typeof expliquerErreurHttp>[2]; values?: Record<string, number> }) {
  const t = useTranslations("Errors");
  const explication = expliquerErreurHttp(status, "internal message, never displayed", code, values);
  return (
    <>
      <p data-testid="titre">{t(explication.titreKey, explication.titreValues)}</p>
      <p data-testid="description">{t(explication.descriptionKey, explication.descriptionValues)}</p>
    </>
  );
}

const ATTENDU: Record<Locale, { titre: string; description: string }> = {
  fr: { titre: "Question refusée par le backend", description: "La question est trop longue (maximum 2000 caractères)." },
  en: { titre: "Question rejected by the backend", description: "The question is too long (maximum 2000 characters)." },
  de: { titre: "Frage vom Backend abgelehnt", description: "Die Frage ist zu lang (maximal 2000 Zeichen)." },
};

describe("Proxy error 'question_too_long' rendered translated (not the raw message)", () => {
  for (const locale of ["fr", "en", "de"] as const) {
    it(`locale='${locale}'`, () => {
      renderAvecIntl(<ErreurRendue status={400} code="question_too_long" values={{ max: 2000 }} />, { locale });

      expect(screen.getByTestId("titre")).toHaveTextContent(ATTENDU[locale].titre);
      expect(screen.getByTestId("description")).toHaveTextContent(ATTENDU[locale].description);
      // The internal message is NEVER displayed when a code is present.
      expect(screen.queryByText(/internal message/)).not.toBeInTheDocument();
    });
  }
});

describe("Proxy error 'backend_unreachable' rendered translated", () => {
  for (const locale of ["fr", "en", "de"] as const) {
    it(`locale='${locale}' never shows the raw internal message`, () => {
      renderAvecIntl(<ErreurRendue status={503} code="backend_unreachable" />, { locale });
      expect(screen.queryByText(/internal message/)).not.toBeInTheDocument();
    });
  }
});
