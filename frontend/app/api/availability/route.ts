import { NextResponse } from "next/server";

import { verifierDisponibilite } from "@/lib/backend";

// LIGHTWEIGHT route, CPU-only on the backend side (Modal "availability"
// function, SEPARATE from the "web" GPU container — see
// backend/app/modal_app.py). This is the ONLY route BackendStatusIndicator
// is allowed to call automatically (every 30s): never /api/health, never
// /api/ask.
export async function GET() {
  const disponible = await verifierDisponibilite();
  return NextResponse.json({ disponible }, { status: disponible ? 200 : 503 });
}
