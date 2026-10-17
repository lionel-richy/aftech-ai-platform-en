import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { DocumentStatusResponse } from "@/lib/types";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const resultat = await appelerBackend<DocumentStatusResponse>(`/documents/${encodeURIComponent(id)}/status`);

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}
