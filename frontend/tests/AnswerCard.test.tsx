import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerCard } from "@/components/assistant/AnswerCard";
import type { AskResponse } from "@/lib/types";
import { renderAvecIntl } from "./test-utils";

function construireReponse(overrides: Partial<AskResponse>): AskResponse {
  return {
    answer: "Default answer.",
    status: "COMPLETE",
    sources: [],
    validated_claims: [],
    timings: { recherche_secondes: 1.18, generation_secondes: 22.96, total_secondes: 24.14 },
    request_id: "req-abc-123",
    ...overrides,
  };
}

describe("AnswerCard", () => {
  it("shows the source documents, their page and their excerpt", () => {
    renderAvecIntl(
      <AnswerCard
        reponse={construireReponse({
          sources: [
            { fichier: "TA-9-2024-0138_EN.pdf", page: 4, extrait: "Extrait page 4", score: 0.8 },
            { fichier: "TA-9-2024-0138_EN.pdf", page: 160, extrait: "Extrait page 160", score: 0.7 },
          ],
        })}
      />,
    );

    expect(screen.getAllByText("TA-9-2024-0138_EN.pdf")).toHaveLength(2);
    expect(screen.getByText("page 4")).toBeInTheDocument();
    expect(screen.getByText("page 160")).toBeInTheDocument();
    expect(screen.getByText("Extrait page 4")).toBeInTheDocument();
  });

  it("explains the PARTIAL status in simple French", () => {
    renderAvecIntl(<AnswerCard reponse={construireReponse({ status: "PARTIAL" })} />);
    expect(screen.getByText(/Seule une partie des affirmations/)).toBeInTheDocument();
  });

  it("explains the NOT_FOUND status in simple French", () => {
    renderAvecIntl(
      <AnswerCard
        reponse={construireReponse({
          status: "NOT_FOUND",
          answer: "Information non trouvée dans les documents.",
        })}
      />,
    );
    expect(screen.getByText(/Aucune affirmation vérifiable/)).toBeInTheDocument();
    expect(screen.getByText("Information non trouvée dans les documents.")).toBeInTheDocument();
  });

  it("shows the request_id in the technical details", () => {
    renderAvecIntl(<AnswerCard reponse={construireReponse({ request_id: "req-xyz-789" })} />);

    fireEvent.click(screen.getByText("Détails techniques"));

    expect(screen.getByText("req-xyz-789")).toBeInTheDocument();
  });

  it("explains the NOT_FOUND status in English when the locale is 'en'", () => {
    renderAvecIntl(
      <AnswerCard
        reponse={construireReponse({
          status: "NOT_FOUND",
          answer: "Information not found in the documents.",
        })}
      />,
      { locale: "en" },
    );
    expect(screen.getByText(/No verifiable statement was found/)).toBeInTheDocument();
  });

  it("explains the PARTIAL status in German when the locale is 'de'", () => {
    renderAvecIntl(<AnswerCard reponse={construireReponse({ status: "PARTIAL" })} />, { locale: "de" });
    expect(screen.getByText(/Nur ein Teil der Aussagen/)).toBeInTheDocument();
  });
});
