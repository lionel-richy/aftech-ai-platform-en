import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/components/assistant/ChatView";
import { etatMoteurActuel, reinitialiserEtatMoteurPourLesTests } from "@/lib/engineStatus";
import { renderAvecIntl } from "./test-utils";

const REPONSE_OK = {
  answer: "Azure offers storage. [source: doc.pdf, page 1]",
  status: "COMPLETE",
  sources: [],
  validated_claims: [],
  timings: { recherche_secondes: 0.1, generation_secondes: 1.0, total_secondes: 1.1 },
  request_id: "req-1",
};

// Part 2 requirement: unlike automatic monitoring (never a GPU route), a
// REAL question must keep starting the engine normally — /api/ask (a GPU
// route) is indeed called, and the shared engine state goes through
// "demarrage" then "pret".
describe("ChatView — a real question keeps starting the engine", () => {
  beforeEach(() => {
    reinitialiserEtatMoteurPourLesTests();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("sends the question to /api/ask and publishes state 'pret' after success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(REPONSE_OK), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<ChatView />);

    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Quel document parle d'Azure ?" } });
    fireEvent.click(screen.getByLabelText("Envoyer la question"));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ask",
      expect.objectContaining({ method: "POST" }),
    );
    // The called route IS indeed a GPU route (normal, expected behavior for
    // a real question — never to be confused with BackendStatusIndicator's
    // automatic ping).
    expect(fetchMock.mock.calls[0][0]).toBe("/api/ask");

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("pret"));
  });

  it("publishes state 'indisponible' if the backend doesn't respond", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    renderAvecIntl(<ChatView />);

    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Une question ?" } });
    fireEvent.click(screen.getByLabelText("Envoyer la question"));

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("indisponible"));
  });

  it("goes through state 'demarrage' while the request is in flight", async () => {
    let resoudre: (v: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resoudre = resolve;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderAvecIntl(<ChatView />);
    const champ = await screen.findByLabelText("Votre question");
    fireEvent.change(champ, { target: { value: "Une question ?" } });

    act(() => {
      fireEvent.click(screen.getByLabelText("Envoyer la question"));
    });

    await waitFor(() => expect(etatMoteurActuel().etat).toBe("demarrage"));

    await act(async () => {
      resoudre(new Response(JSON.stringify(REPONSE_OK), { status: 200 }));
      await Promise.resolve();
    });
  });
});
