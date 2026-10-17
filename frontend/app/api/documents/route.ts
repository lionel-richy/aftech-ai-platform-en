import { NextResponse } from "next/server";

import { appelerBackend } from "@/lib/backend";
import type { DocumentItem, DocumentUploadResponse } from "@/lib/types";

export async function GET() {
  const resultat = await appelerBackend<DocumentItem[]>("/documents");

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data);
}

export async function POST(request: Request) {
  const formulaire = await request.formData();
  const fichier = formulaire.get("fichier");

  if (!(fichier instanceof Blob) || !fichier.size) {
    return NextResponse.json({ message: "No file received.", code: "no_file" }, { status: 400 });
  }

  // We do NOT re-validate the type/signature here: the backend (pypdf +
  // real binary verification, see document_pipeline.py) is the only source
  // of truth, exactly like response_language for /ask.
  const resultat = await appelerBackend<DocumentUploadResponse>("/documents", {
    methode: "POST",
    corps: formulaire,
    timeoutMs: 60000,
  });

  if (!resultat.ok) {
    return NextResponse.json(
      { message: resultat.message, code: resultat.code, values: resultat.values },
      { status: resultat.status },
    );
  }

  return NextResponse.json(resultat.data, { status: 201 });
}
