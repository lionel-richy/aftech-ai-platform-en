import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { GET, POST } from "@/app/api/documents/route";

// jsdom (test environment) and Node's native "Request" (used by
// next/server) have incompatible FormData/File implementations (a known
// interop bug, not specific to this project): building a real FormData THEN
// passing it as a real Request's body fails with an internal WebIDL error,
// even outside any application code. We work around it by mocking
// .formData() directly instead of serializing a real Request — what
// request.formData() returns IS a real jsdom FormData, so `instanceof
// Blob`/`.size` on the route.ts side are still genuinely tested.
function requeteAvecFichier(nom: string, contenu: string, type = "application/pdf") {
  const formulaire = new FormData();
  formulaire.append("fichier", new File([contenu], nom, { type }));
  return { formData: async () => formulaire } as unknown as Request;
}

describe("POST /api/documents (upload proxy)", () => {
  it("rejects a request with no file, with code='no_file', WITHOUT calling the backend", async () => {
    const requete = { formData: async () => new FormData() } as unknown as Request;

    const reponse = await POST(requete);
    const corps = await reponse.json();

    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("no_file");
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("passes the FormData through to appelerBackend as-is (no JSON.stringify)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { id: "abc", nom_original: "rapport.pdf", statut: "UPLOADED" },
    });

    const reponse = await POST(requeteAvecFichier("rapport.pdf", "contenu-pdf"));
    const corps = await reponse.json();

    expect(reponse.status).toBe(201);
    expect(corps.statut).toBe("UPLOADED");
    expect(appelerBackend).toHaveBeenCalledWith(
      "/documents",
      expect.objectContaining({ methode: "POST", corps: expect.any(FormData) }),
    );
  });

  it("relays a 422 (invalid file on the backend side) with its code", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 422,
      message: "The PDF file is corrupted or unreadable.",
    });

    const reponse = await POST(requeteAvecFichier("corrompu.pdf", "xx"));
    expect(reponse.status).toBe(422);
  });

  it("relays a 409 (duplicate detected by the backend)", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 409,
      message: "This document (identical content) is already indexed.",
    });

    const reponse = await POST(requeteAvecFichier("copie.pdf", "contenu-pdf"));
    expect(reponse.status).toBe(409);
  });
});

describe("GET /api/documents (list, unchanged)", () => {
  it("relays the list as-is", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: [] });
    const reponse = await GET();
    expect(reponse.status).toBe(200);
    expect(await reponse.json()).toEqual([]);
  });
});
