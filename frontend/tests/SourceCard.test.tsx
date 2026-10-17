import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceCard } from "@/components/assistant/SourceCard";
import type { SourceItem } from "@/lib/types";
import { renderAvecIntl } from "./test-utils";

const SOURCE: SourceItem = {
  fichier: "politique_securite.txt",
  page: 1,
  extrait: "Les mots de passe doivent contenir au moins 14 caractères.",
  score: 0.912,
};

describe("SourceCard", () => {
  it("shows the file, the page and the excerpt", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.getByText("politique_securite.txt")).toBeInTheDocument();
    expect(screen.getByText("page 1")).toBeInTheDocument();
    expect(screen.getByText(SOURCE.extrait)).toBeInTheDocument();
  });

  it("hides the score by default (only visible in technical details)", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />);
    expect(screen.queryByText(/score sémantique/)).not.toBeInTheDocument();
  });

  it("shows the score when requested", () => {
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore />);
    expect(screen.getByText(/score sémantique : 0.912/)).toBeInTheDocument();
  });

  it("keeps the file and excerpt in their original language even in English", () => {
    // Requirement: exact citations/excerpts are NEVER translated, regardless
    // of the interface language.
    renderAvecIntl(<SourceCard source={SOURCE} afficherScore={false} />, { locale: "en" });
    expect(screen.getByText("politique_securite.txt")).toBeInTheDocument();
    expect(screen.getByText(SOURCE.extrait)).toBeInTheDocument();
    // Only the structural label ("page") is translated.
    expect(screen.getByText("page 1")).toBeInTheDocument();
  });
});
