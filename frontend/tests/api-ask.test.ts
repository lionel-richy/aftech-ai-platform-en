import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/backend", () => ({
  appelerBackend: vi.fn(),
}));

import { appelerBackend } from "@/lib/backend";
import { POST } from "@/app/api/ask/route";
import type { AskResponse } from "@/lib/types";

function requeteJson(corps: unknown) {
  return new Request("http://localhost/api/ask", {
    method: "POST",
    body: JSON.stringify(corps),
    headers: { "Content-Type": "application/json" },
  });
}

const REPONSE_COMPLETE: AskResponse = {
  answer: "14 characters minimum.",
  status: "COMPLETE",
  sources: [],
  validated_claims: [],
  timings: { recherche_secondes: 0.1, generation_secondes: 1.2, total_secondes: 1.3 },
  request_id: "abc-123",
};

describe("POST /api/ask", () => {
  it("rejects an empty question WITHOUT calling the backend, with code='empty_question'", async () => {
    const reponse = await POST(requeteJson({ question: "" }));
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("empty_question");
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("rejects a question longer than 2000 characters, with code='question_too_long' and values.max", async () => {
    const reponse = await POST(requeteJson({ question: "a".repeat(2001) }));
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("question_too_long");
    expect(corps.values).toEqual({ max: 2000 });
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("rejects an invalid JSON body, with code='invalid_json'", async () => {
    const requete = new Request("http://localhost/api/ask", {
      method: "POST",
      body: "{this is not json",
      headers: { "Content-Type": "application/json" },
    });
    const reponse = await POST(requete);
    const corps = await reponse.json();
    expect(reponse.status).toBe(400);
    expect(corps.code).toBe("invalid_json");
    expect(appelerBackend).not.toHaveBeenCalled();
  });

  it("relays a COMPLETE status as-is", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    const reponse = await POST(requeteJson({ question: "What is the minimum length?" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(200);
    expect(corps.status).toBe("COMPLETE");
  });

  it("relays a PARTIAL status as-is", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { ...REPONSE_COMPLETE, status: "PARTIAL" },
    });

    const reponse = await POST(requeteJson({ question: "What are the ongoing projects?" }));
    const corps = await reponse.json();
    expect(corps.status).toBe("PARTIAL");
  });

  it("relays a NOT_FOUND status as-is", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: true,
      data: { ...REPONSE_COMPLETE, status: "NOT_FOUND", answer: "Information not found in the documents." },
    });

    const reponse = await POST(requeteJson({ question: "What is AFTECH's revenue?" }));
    const corps = await reponse.json();
    expect(corps.status).toBe("NOT_FOUND");
  });

  it("passes response_language='de' through to the backend as-is", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    await POST(requeteJson({ question: "Welches Dokument?", response_language: "de" }));

    expect(appelerBackend).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ corps: expect.objectContaining({ response_language: "de" }) }),
    );
  });

  it("defaults response_language to 'fr' if absent from the request", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({ ok: true, data: REPONSE_COMPLETE });

    await POST(requeteJson({ question: "Hello?" }));

    expect(appelerBackend).toHaveBeenCalledWith(
      "/ask",
      expect.objectContaining({ corps: expect.objectContaining({ response_language: "fr" }) }),
    );
  });

  it("relays a 422 (invalid language rejected by the backend) WITHOUT transforming it", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 422,
      message: "response_language: value not allowed",
    });

    const reponse = await POST(requeteJson({ question: "Hello?", response_language: "es" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(422);
    expect(corps.message).toContain("response_language");
  });

  it("relays a 503 backend-unavailable WITHOUT a traceback", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 503,
      message: "Could not reach the backend (unavailable?).",
    });

    const reponse = await POST(requeteJson({ question: "Hello?" }));
    const corps = await reponse.json();

    expect(reponse.status).toBe(503);
    expect(corps.message).not.toMatch(/Traceback/i);
  });

  it("relays the code and values of an error coming from lib/backend.ts (e.g. 'backend_unreachable')", async () => {
    vi.mocked(appelerBackend).mockResolvedValue({
      ok: false,
      status: 503,
      message: "Could not reach the backend (unavailable?).",
      code: "backend_unreachable",
    });

    const reponse = await POST(requeteJson({ question: "Hello?" }));
    const corps = await reponse.json();

    expect(corps.code).toBe("backend_unreachable");
  });
});
