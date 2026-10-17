import { Database, Folder, GitBranch, GitFork, HardDrive, KanbanSquare } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";

// All "Not connected" for this Demo V1 — no fake functional connector.
// Generic icons (lucide-react no longer includes brand logos).
// Product names (Jira Cloud, SharePoint, …) are proper nouns: they are
// never translated.
const INTEGRATIONS = [
  { nomKey: "jiraCloud" as const, icone: KanbanSquare, noteKey: "jiraNote" as const },
  { nomKey: "sharepoint" as const, icone: HardDrive },
  { nomKey: "onedrive" as const, icone: HardDrive },
  { nomKey: "googleDrive" as const, icone: HardDrive },
  { nomKey: "localFolders" as const, icone: Folder },
  { nomKey: "github" as const, icone: GitFork },
  { nomKey: "gitlab" as const, icone: GitBranch },
  { nomKey: "databases" as const, icone: Database },
] as const;

export default async function IntegrationsPage() {
  const tNav = await getTranslations("Nav");
  const t = await getTranslations("Integrations");

  return (
    <>
      <Topbar title={tNav("integrations")} description={t("topbarDescription")} />
      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATIONS.map((integration) => (
            <IntegrationCard
              key={integration.nomKey}
              nom={t(integration.nomKey)}
              icone={<integration.icone aria-hidden className="h-5 w-5 text-[var(--text-secondary)]" />}
              etat="non_connecte"
              note={"noteKey" in integration ? t(integration.noteKey) : undefined}
            />
          ))}
        </div>
      </main>
    </>
  );
}
