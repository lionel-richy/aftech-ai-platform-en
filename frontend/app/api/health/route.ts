import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { HealthResponse } from "@/lib/types";

export async function GET() {
  const resultat = await appelerBackend<HealthResponse>("/health", { authentifie: false });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}
