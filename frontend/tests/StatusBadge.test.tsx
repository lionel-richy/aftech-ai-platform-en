import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { renderAvecIntl } from "./test-utils";

describe("StatusBadge", () => {
  it("shows COMPLETE in French", () => {
    renderAvecIntl(<StatusBadge status="COMPLETE" />);
    expect(screen.getByText(/Complet/)).toBeInTheDocument();
    expect(screen.getByText(/COMPLETE/)).toBeInTheDocument();
  });

  it("shows PARTIAL in French", () => {
    renderAvecIntl(<StatusBadge status="PARTIAL" />);
    expect(screen.getByText(/Partiel/)).toBeInTheDocument();
  });

  it("shows NOT_FOUND in French", () => {
    renderAvecIntl(<StatusBadge status="NOT_FOUND" />);
    expect(screen.getByText(/Non trouvé/)).toBeInTheDocument();
  });

  it("shows COMPLETE in English when the locale is 'en'", () => {
    renderAvecIntl(<StatusBadge status="COMPLETE" />, { locale: "en" });
    expect(screen.getByText(/Complete/)).toBeInTheDocument();
  });

  it("shows NOT_FOUND in German when the locale is 'de'", () => {
    renderAvecIntl(<StatusBadge status="NOT_FOUND" />, { locale: "de" });
    expect(screen.getByText(/Nicht gefunden/)).toBeInTheDocument();
  });
});
