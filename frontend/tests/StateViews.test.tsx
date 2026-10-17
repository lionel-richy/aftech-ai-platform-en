import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BackendUnavailableState, EmptyState, ErrorState, LoadingState } from "@/components/ui/StateViews";
import { renderAvecIntl } from "./test-utils";

describe("Shared states (loading / empty / error / backend unavailable)", () => {
  it("LoadingState shows a loading message", () => {
    renderAvecIntl(<LoadingState label="Loading the dashboard…" />);
    expect(screen.getByText("Loading the dashboard…")).toBeInTheDocument();
  });

  it("LoadingState shows the translated default label if none is provided", () => {
    renderAvecIntl(<LoadingState />, { locale: "en" });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("EmptyState shows the title and the description", () => {
    renderAvecIntl(<EmptyState title="No documents" description="Nothing to show." />);
    expect(screen.getByText("No documents")).toBeInTheDocument();
    expect(screen.getByText("Nothing to show.")).toBeInTheDocument();
  });

  it("ErrorState shows the error title", () => {
    renderAvecIntl(<ErrorState title="Loading error" />);
    expect(screen.getByText("Loading error")).toBeInTheDocument();
  });

  it("BackendUnavailableState shows the standard label", () => {
    renderAvecIntl(<BackendUnavailableState />);
    expect(screen.getByText("Backend indisponible")).toBeInTheDocument();
  });

  it("BackendUnavailableState shows a custom description if provided", () => {
    renderAvecIntl(<BackendUnavailableState description="No CUDA GPU detected." />);
    expect(screen.getByText("No CUDA GPU detected.")).toBeInTheDocument();
  });

  it("BackendUnavailableState shows the standard label in German", () => {
    renderAvecIntl(<BackendUnavailableState />, { locale: "de" });
    expect(screen.getByText("Backend nicht verfügbar")).toBeInTheDocument();
  });
});
