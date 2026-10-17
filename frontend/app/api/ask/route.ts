import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { AskResponse } from "@/lib/types";

const LIMITE_QUESTION_CARACTERES = 2000;

export async function POST(request: Request) {
  let corps: { question?: unknown; top_k?: unknown; response_language?: unknown };
  try {
    corps = await request.json();
  } catch {
    // "message" stays internal (log/debug only): it's "code" that drives
    // the translated text shown on the client side (see lib/errorMessages.ts).
    return NextResponse.json(
      { message: "Invalid JSON request body.", code: "invalid_json" },
      { status: 400 },
    );
  }

  const question = typeof corps.question === "string" ? corps.question : "";
  if (!question.trim()) {
    return NextResponse.json({ message: "The question is empty.", code: "empty_question" }, { status: 400 });
  }
  if (question.length > LIMITE_QUESTION_CARACTERES) {
    return NextResponse.json(
      {
        message: `Question too long (max ${LIMITE_QUESTION_CARACTERES} characters).`,
        code: "question_too_long",
        values: { max: LIMITE_QUESTION_CARACTERES },
      },
      { status: 400 },
    );
  }

  // response_language is NOT re-validated here: the backend (schemas.py,
  // AskRequest.response_language: Literal["fr","en","de"]) is the only
  // source of truth and returns 422 if the value is invalid — this proxy
  // just passes it through, defaulting to "fr" if absent.
  const resultat = await appelerBackend<AskResponse>("/ask", {
    methode: "POST",
    corps: {
      question,
      top_k: typeof corps.top_k === "number" ? corps.top_k : 8,
      response_language: typeof corps.response_language === "string" ? corps.response_language : "fr",
    },
    // At least 300s: a cold Modal start (download + loading Qwen on a brand
    // new GPU container) can take several minutes.
    timeoutMs: 300000,
  });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}
