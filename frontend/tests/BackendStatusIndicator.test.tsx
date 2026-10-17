import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BackendStatusIndicator } from "@/components/layout/BackendStatusIndicator";
import { definirEtatMoteur, reinitialiserEtatMoteurPourLesTests } from "@/lib/engineStatus";
import { renderAvecIntl } from "./test-utils";

// Core requirement of Part 2: AUTOMATIC monitoring (this component, mounted
// on every page) must NEVER call a GPU route (/api/health, /api/ask) — only
// /api/availability (CPU, separate Modal function). Otherwise Modal never
// scales back down to zero after scaledown_window=300 (a real bug fixed
// here).
describe("BackendStatusIndicator — never calls a GPU route", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    reinitialiserEtatMoteurPourLesTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("calls ONLY /api/availability on mount, never /api/health or /api/ask", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/availability", expect.anything());
    expect(fetchMock).not.toHaveBeenCalledWith("/api/health", expect.anything());
    expect(fetchMock).not.toHaveBeenCalledWith("/api/ask", expect.anything());

    vi.unstubAllGlobals();
  });

  it("never keeps a loop going to a GPU route, even after many 30s cycles", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    // Simulates 2 hours with the tab open (240 cycles of 30s): exactly the
    // scenario that, before the fix, indefinitely prevented scale-to-zero.
    for (let i = 0; i < 240; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(30000);
        await Promise.resolve();
      });
    }

    expect(fetchMock.mock.calls.length).toBeGreaterThan(1);
    for (const appel of fetchMock.mock.calls) {
      expect(appel[0]).toBe("/api/availability");
    }

    vi.unstubAllGlobals();
  });

  it("the engine's detailed state (starting/ready/unavailable) NEVER changes on its own: only a real interaction does", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ disponible: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<BackendStatusIndicator />);
    await act(async () => {
      await Promise.resolve();
    });

    // Without any real question or manual check: the API is available, but
    // the engine stays IDLE indefinitely.
    for (let i = 0; i < 10; i += 1) {
      await act(async () => {
        vi.advanceTimersByTime(30000);
        await Promise.resolve();
      });
    }
    expect(screen.getByRole("status")).toHaveAttribute("title", expect.stringContaining("veille"));

    // A REAL interaction (simulated here directly, as ChatView would after
    // a real question) does change the display.
    await act(async () => {
      definirEtatMoteur({ etat: "pret", vramUtiliseeOctets: 1_000_000, vramTotaleOctets: 2_000_000 });
    });
    expect(screen.getByRole("status")).toHaveAttribute("title", expect.stringContaining("prêt"));

    vi.unstubAllGlobals();
  });
});
