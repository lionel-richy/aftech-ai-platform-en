import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { GET } from "@/app/api/documents/[id]/status/route";
import { DELETE } from "@/app/api/documents/[id]/route";

function requeteAvecParams(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("GET /api/documents/[id]/status", () => {
  it("calls the backend on the correctly encoded path", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: {
        id: "abc 123",
        nom_original: "x.pdf",
        statut: "READY",
        message_erreur: null,
        nb_pages: 1,
        nb_passages: 2,
        date_ajout: "2026-01-01T00:00:00Z",
      },
    });

    const reponse = await GET(new Request("http://localhost"), requeteAvecParams("abc 123"));
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.statut).toBe("READY");
    expect(appelerBackend).toHaveBeenCalledWith("/documents/abc%20123/status");
  });

  it("relays a 404 (document not found)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: false, status: 404, message: "Document not found." });

    const reponse = await GET(new Request("http://localhost"), requeteAvecParams("inconnu"));
    expect(reponse.status).toBe(404);
  });
});

describe("DELETE /api/documents/[id]", () => {
  it("returns 204 with no body when the deletion succeeds", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: undefined });

    const reponse = await DELETE(new Request("http://localhost"), requeteAvecParams("abc123"));

    expect(reponse.status).toBe(204);
    expect(appelerBackend).toHaveBeenCalledWith(
      "/documents/abc123",
      expect.objectContaining({ methode: "DELETE" }),
    );
  });

  it("relays a 409 (rebuild already in progress)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 409,
      message: "An index rebuild is already in progress — try again shortly.",
    });

    const reponse = await DELETE(new Request("http://localhost"), requeteAvecParams("abc123"));
    expect(reponse.status).toBe(409);
  });
});
