import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const resultat = await appelerBackend<undefined>(`/documents/${encodeURIComponent(id)}`, {
    methode: "DELETE",
    timeoutMs: 60000,
  });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return new NextResponse(null, { status: 204 });
}
