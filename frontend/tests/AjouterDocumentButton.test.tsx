import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AjouterDocumentButton } from "@/components/bibliotheque/AjouterDocumentButton";
import { renderAvecIntl } from "./test-utils";

function ouvrirLeVolet() {
  fireEvent.click(screen.getByText("Ajouter un document"));
}

describe("AjouterDocumentButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the accessible drop zone (role + label) once opened", () => {
    renderAvecIntl(<AjouterDocumentButton />);
    ouvrirLeVolet();
    expect(screen.getByRole("button", { name: "Déposez un PDF ici, ou cliquez pour en choisir un" })).toBeInTheDocument();
  });

  it("shows the drop zone in English when the locale is 'en'", () => {
    renderAvecIntl(<AjouterDocumentButton />, { locale: "en" });
    fireEvent.click(screen.getByText("Add a document"));
    expect(screen.getByRole("button", { name: "Drop a PDF here, or click to choose one" })).toBeInTheDocument();
  });

  it("shows the drop zone in German when the locale is 'de'", () => {
    renderAvecIntl(<AjouterDocumentButton />, { locale: "de" });
    fireEvent.click(screen.getByText("Dokument hinzufügen"));
    expect(screen.getByRole("button", { name: "PDF hier ablegen oder klicken, um eines auszuwählen" })).toBeInTheDocument();
  });

  it("successful upload: sends the file, follows the status until READY, notifies the parent", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/documents") {
        return new Response(JSON.stringify({ id: "abc", nom_original: "x.pdf", statut: "UPLOADED" }), { status: 201 });
      }
      if (url === "/api/documents/abc/status") {
        return new Response(
          JSON.stringify({
            id: "abc",
            nom_original: "x.pdf",
            statut: "READY",
            message_erreur: null,
            nb_pages: 1,
            nb_passages: 2,
            date_ajout: "2026-01-01T00:00:00Z",
          }),
          { status: 200 },
        );
      }
      throw new Error(`Unexpected URL in this test: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDocumentAjoute = vi.fn();

    renderAvecIntl(<AjouterDocumentButton onDocumentAjoute={onDocumentAjoute} />);
    ouvrirLeVolet();

    const input = screen.getByLabelText("Déposez un PDF ici, ou cliquez pour en choisir un", {
      selector: "input",
    }) as HTMLInputElement;
    const fichier = new File(["contenu"], "x.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [fichier] } });

    await waitFor(() => expect(onDocumentAjoute).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/documents");
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ method: "POST" }));
  });

  it("rejected upload (422): shows the error WITHOUT calling the status endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "x", code: "backend_error_status", values: { status: 422 } }), {
        status: 422,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<AjouterDocumentButton />);
    ouvrirLeVolet();
    const input = screen.getByLabelText("Déposez un PDF ici, ou cliquez pour en choisir un", {
      selector: "input",
    }) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "x.pdf", { type: "application/pdf" })] } });

    await waitFor(() => expect(screen.getByText("Une erreur imprévue est survenue.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
