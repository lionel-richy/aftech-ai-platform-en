import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentCard } from "@/components/bibliotheque/DocumentCard";
import type { DocumentItem } from "@/lib/types";
import { renderAvecIntl } from "./test-utils";

function construireDocument(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    nom_fichier: "rapport.pdf",
    pages: 10,
    passages: 20,
    hash_sha256: "abcdef0123456789",
    modele_embeddings: "BAAI/bge-m3",
    date_index: "2026-01-01T00:00:00Z",
    supprimable: false,
    ...overrides,
  };
}

describe("DocumentCard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows 'Indexé' for a historical document (not deletable, no delete button)", () => {
    renderAvecIntl(<DocumentCard document={construireDocument()} />);
    expect(screen.getByText("Indexé")).toBeInTheDocument();
    expect(screen.queryByText("Supprimer")).not.toBeInTheDocument();
  });

  it("shows the FAILED status with the error message", () => {
    renderAvecIntl(
      <DocumentCard
        document={construireDocument({
          id: "abc",
          statut: "FAILED",
          message_erreur: "The PDF file is corrupted or unreadable.",
          supprimable: true,
        })}
      />,
    );
    expect(screen.getByText("Échec")).toBeInTheDocument();
    expect(screen.getByText("The PDF file is corrupted or unreadable.")).toBeInTheDocument();
  });

  it("shows the status in English when the locale is 'en'", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "a", statut: "INDEXING", supprimable: true })} />, {
      locale: "en",
    });
    expect(screen.getByText("Indexing…")).toBeInTheDocument();
  });

  it("shows the status in German when the locale is 'de'", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "a", statut: "EXTRACTING", supprimable: true })} />, {
      locale: "de",
    });
    expect(screen.getByText("Text wird extrahiert…")).toBeInTheDocument();
  });

  it("the filename is NEVER translated, regardless of the locale", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ nom_fichier: "Rapport_Confidentiel_2026.pdf" })} />, {
      locale: "de",
    });
    expect(screen.getByText("Rapport_Confidentiel_2026.pdf")).toBeInTheDocument();
  });

  it("a deletable document shows the Delete button, then asks for confirmation", () => {
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));

    expect(screen.getByText("Supprimer ce document ?")).toBeInTheDocument();
    expect(screen.getByText("Oui, supprimer")).toBeInTheDocument();
    expect(screen.getByText("Annuler")).toBeInTheDocument();
  });

  it("canceling closes the confirmation without deleting anything", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Annuler"));

    expect(screen.queryByText("Supprimer ce document ?")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirming calls DELETE /api/documents/{id} and notifies the parent on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const onSupprime = vi.fn();
    renderAvecIntl(
      <DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} onSupprime={onSupprime} />,
    );

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Oui, supprimer"));

    await waitFor(() => expect(onSupprime).toHaveBeenCalledWith("abc"));
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/abc", { method: "DELETE" });
  });

  it("shows an error if the deletion fails, without crashing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
    renderAvecIntl(<DocumentCard document={construireDocument({ id: "abc", statut: "READY", supprimable: true })} />);

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(screen.getByText("Oui, supprimer"));

    await waitFor(() => expect(screen.getByText("La suppression a échoué. Réessayez.")).toBeInTheDocument());
  });
});
