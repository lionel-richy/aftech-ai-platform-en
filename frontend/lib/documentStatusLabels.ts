import type { DocumentStatus } from "./types";

// Shared between DocumentCard.tsx (badge on the list) and
// AjouterDocumentButton.tsx (progress during upload) — "Bibliotheque"
// namespace in messages/{locale}.json.
export const CLE_STATUT: Record<
  Exclude<DocumentStatus, "READY">,
  "statusUploaded" | "statusExtracting" | "statusIndexing" | "statusFailed" | "statusDeleting"
> = {
  UPLOADED: "statusUploaded",
  EXTRACTING: "statusExtracting",
  INDEXING: "statusIndexing",
  FAILED: "statusFailed",
  DELETING: "statusDeleting",
};
