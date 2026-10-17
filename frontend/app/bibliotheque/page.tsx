import { getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { BackendUnavailableState, ErrorState, EmptyState } from "@/components/ui/StateViews";
import { BibliothequeView } from "@/components/bibliotheque/BibliothequeView";
import { appelerBackend } from "@/lib/backend";
import type { DocumentItem } from "@/lib/types";

// Real data on every request (backend): never statically prerendered.
export const instant = false;

export default async function BibliothequePage() {
  const resultat = await appelerBackend<DocumentItem[]>("/documents");
  const tNav = await getTranslations("Nav");
  const t = await getTranslations("Bibliotheque");

  return (
    <>
      <Topbar title={tNav("bibliotheque")} description={t("topbarDescription")} />
      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        {!resultat.ok && resultat.status === 503 && (
          <BackendUnavailableState description={resultat.message} />
        )}
        {!resultat.ok && resultat.status !== 503 && (
          <ErrorState title={t("errorLoadingTitle")} description={resultat.message} />
        )}
        {resultat.ok && resultat.data.length === 0 && (
          <EmptyState title={t("emptyNoDocumentsTitle")} description={t("emptyNoDocumentsDescription")} />
        )}
        {resultat.ok && resultat.data.length > 0 && <BibliothequeView documents={resultat.data} />}
      </main>
    </>
  );
}
