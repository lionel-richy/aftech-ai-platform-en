// SERVER ONLY. This file reads BACKEND_API_KEY (never NEXT_PUBLIC_) and must
// only be imported from app/api/*/route.ts (Next.js server routes). The
// browser always calls our /api/* routes, never Modal/the backend directly.
//
// Environment variables (frontend/.env.local, never committed):
//   BACKEND_BASE_URL  e.g. https://<workspace>--aftech-ai-platform-web.modal.run
//   BACKEND_API_KEY   same value as the Modal secret "aftech-backend-secrets"
import "server-only";

import type { BackendResult } from "./types";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;
// URL of the Modal "availability" function (CPU only, NO GPU — see
// backend/app/modal_app.py). Deliberately SEPARATE from BACKEND_BASE_URL.
const BACKEND_AVAILABILITY_URL = process.env.BACKEND_AVAILABILITY_URL ?? "http://localhost:8000";

interface AppelBackendOptions {
  methode?: "GET" | "POST" | "DELETE";
  // FormData: passed through as-is (multipart upload) — Content-Type and its
  // boundary are set automatically by fetch, NEVER by us (otherwise the
  // declared boundary would no longer match the real body).
  corps?: unknown | FormData;
  authentifie?: boolean; // false for /health, which doesn't require a key
  timeoutMs?: number;
}

export async function appelerBackend<T>(
  chemin: string,
  options: AppelBackendOptions = {},
): Promise<BackendResult<T>> {
  const { methode = "GET", corps, authentifie = true, timeoutMs = 15000 } = options;

  if (authentifie && !BACKEND_API_KEY) {
    return {
      ok: false,
      status: 500,
      code: "api_key_missing",
      message: "BACKEND_API_KEY is not configured on the Next.js server.",
    };
  }

  const estFormData = typeof FormData !== "undefined" && corps instanceof FormData;
  const entetes: Record<string, string> = estFormData ? {} : { "Content-Type": "application/json" };
  if (authentifie) {
    entetes.Authorization = `Bearer ${BACKEND_API_KEY}`;
  }

  const controleur = new AbortController();
  const minuteur = setTimeout(() => controleur.abort(), timeoutMs);

  try {
    const reponse = await fetch(`${BACKEND_BASE_URL}${chemin}`, {
      method: methode,
      headers: entetes,
      body: estFormData ? (corps as FormData) : corps !== undefined ? JSON.stringify(corps) : undefined,
      signal: controleur.signal,
      cache: "no-store",
    });

    if (!reponse.ok) {
      let message = `The backend responded ${reponse.status}.`;
      // "code" is only set for the generic message above (which WE
      // generate): if the backend returned its own "detail", that text
      // remains an untranslated passthrough (like a citation), with no code.
      let code: "backend_error_status" | undefined = "backend_error_status";
      try {
        const corpsErreur = await reponse.json();
        if (typeof corpsErreur?.detail === "string") {
          message = corpsErreur.detail;
          code = undefined;
        }
      } catch {
        // Non-JSON body: keep the generic message above.
      }
      return { ok: false, status: reponse.status, message, code, values: code ? { status: reponse.status } : undefined };
    }

    if (reponse.status === 204) {
      return { ok: true, data: undefined as T };
    }
    const donnees = (await reponse.json()) as T;
    return { ok: true, data: donnees };
  } catch (erreur) {
    const estTimeout = erreur instanceof Error && erreur.name === "AbortError";
    // 504 (timeout) and 503 (unreachable) are deliberately distinct: the
    // frontend shows a different explanation depending on the case (see
    // lib/errorMessages.ts) — a cold start that's taking too long is not the
    // same situation as a fully stopped backend.
    return {
      ok: false,
      status: estTimeout ? 504 : 503,
      code: estTimeout ? "timeout_no_response" : "backend_unreachable",
      message: estTimeout
        ? "The backend did not respond in time (cold start taking too long?)."
        : "Could not reach the backend (unavailable?).",
    };
  } finally {
    clearTimeout(minuteur);
  }
}

// LIGHTWEIGHT, CPU-only ping: queries the Modal "availability" function
// (never "web", which carries the GPU), with no key (no sensitive
// information returned). This is the ONLY route the frontend's automatic
// monitoring (BackendStatusIndicator) is allowed to call in a loop — never
// /health, never /ask: see docs/MODAL_COST_SAFETY.md.
export async function verifierDisponibilite(timeoutMs = 5000): Promise<boolean> {
  const controleur = new AbortController();
  const minuteur = setTimeout(() => controleur.abort(), timeoutMs);
  try {
    const reponse = await fetch(`${BACKEND_AVAILABILITY_URL}/availability`, {
      signal: controleur.signal,
      cache: "no-store",
    });
    return reponse.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(minuteur);
  }
}
