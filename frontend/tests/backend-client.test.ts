import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// lib/backend.ts imports "server-only", which deliberately throws when
// resolved under the "browser" condition (the case in this project's global
// jsdom environment, used for component tests). We therefore replace that
// module with a no-op for THIS file, which tests lib/backend.ts's own logic,
// not the bundling guard-rail itself.
vi.mock("server-only", () => ({}));

const CLE_TEST = "test-secret-key-never-expose";

describe("appelerBackend (server client -> FastAPI)", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_BASE_URL", "http://backend-test:8000");
    vi.stubEnv("BACKEND_API_KEY", CLE_TEST);
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("adds the Authorization header with the server key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    await appelerBackend("/documents");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe(`Bearer ${CLE_TEST}`);
  });

  it("does NOT add the Authorization header when authentifie=false (/health)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    await appelerBackend("/health", { authentifie: false });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("returns a 503 error and does not throw when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("fetch failed")));

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/ask", { methode: "POST", corps: { question: "x" } });

    expect(resultat.ok).toBe(false);
    if (!resultat.ok) {
      expect(resultat.status).toBe(503);
      expect(resultat.message.toLowerCase()).toContain("backend");
    }
  });

  it("returns 504 (not 503) when the request times out (timeout, cold start)", async () => {
    const erreurAbort = new Error("The operation was aborted");
    erreurAbort.name = "AbortError";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(erreurAbort));

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/ask", { methode: "POST", corps: { question: "x" }, timeoutMs: 10 });

    expect(resultat.ok).toBe(false);
    if (!resultat.ok) {
      expect(resultat.status).toBe(504);
      expect(resultat.message.toLowerCase()).toContain("time");
    }
  });

  it("refuses the call if BACKEND_API_KEY is not configured", async () => {
    vi.stubEnv("BACKEND_API_KEY", "");
    vi.resetModules();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { appelerBackend } = await import("@/lib/backend");
    const resultat = await appelerBackend("/documents");

    expect(resultat.ok).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("verifierDisponibilite (CPU ping, Part 2)", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_AVAILABILITY_URL", "http://availability-test:9000");
    // Deliberately NO BACKEND_API_KEY here: this function must NEVER need
    // one (no sensitive information returned).
    vi.stubEnv("BACKEND_API_KEY", "");
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("calls BACKEND_AVAILABILITY_URL + '/availability', NEVER BACKEND_BASE_URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    await verifierDisponibilite();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("http://availability-test:9000/availability");
  });

  it("NEVER adds an Authorization header (no key needed)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    await verifierDisponibilite();

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.headers).toBeUndefined();
  });

  it("works even without BACKEND_API_KEY configured (unlike appelerBackend)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns false (never throws) when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(false);
  });

  it("returns false when the response is not ok (e.g. 503)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));

    const { verifierDisponibilite } = await import("@/lib/backend");
    const disponible = await verifierDisponibilite();

    expect(disponible).toBe(false);
  });
});
