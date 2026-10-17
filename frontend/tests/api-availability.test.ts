import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  verifierDisponibilite: vi.fn(),
}));

import { verifierDisponibilite } from "@/lib/backend";
import { GET } from "@/app/api/availability/route";

describe("GET /api/availability (lightweight route, CPU-only on the backend side)", () => {
  it("returns 200 and disponible=true when verifierDisponibilite() succeeds", async () => {
    vi.mocked(verifierDisponibilite).mockResolvedValue(true);

    const reponse = await GET();
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.disponible).toBe(true);
  });

  it("returns 503 and disponible=false when verifierDisponibilite() fails", async () => {
    vi.mocked(verifierDisponibilite).mockResolvedValue(false);

    const reponse = await GET();
    const corps = await reponse.json();

    expect(reponse.status).toBe(503);
    expect(corps.disponible).toBe(false);
  });
});
