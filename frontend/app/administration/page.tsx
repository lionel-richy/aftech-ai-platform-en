import { getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { Card, DemoBadge } from "@/components/ui/Card";
import { DemoBanner } from "@/components/administration/DemoBanner";

// FICTIONAL data, to preview the screen before the real multi-tenant system
// exists. Never presented as real (see DemoBadge). Names and dates remain
// opaque sample data (not translated, like identifiers); only
// roles/statuses/events are translated.
const UTILISATEURS_DEMO = [
  { nom: "A. Dubois", roleKey: "roleOrgAdmin", statutKey: "statusActive" },
  { nom: "M. Nguyen", roleKey: "roleAiManager", statutKey: "statusActive" },
  { nom: "S. Okafor", roleKey: "roleUser", statutKey: "statusActive" },
  { nom: "J. Moreau", roleKey: "roleAuditor", statutKey: "statusInvited" },
] as const;

const ROLES_PREPARES = [
  { nomKey: "roleOrgAdmin", descriptionKey: "roleOrgAdminDesc" },
  { nomKey: "roleAiManager", descriptionKey: "roleAiManagerDesc" },
  { nomKey: "roleUser", descriptionKey: "roleUserDesc" },
  { nomKey: "roleAuditor", descriptionKey: "roleAuditorDesc" },
] as const;

const MODELES_AUTORISES_DEMO = [
  { nom: "Qwen/Qwen3-4B-Instruct-2507", usageKey: "modelGenActive" },
  { nom: "BAAI/bge-m3", usageKey: "modelEmbedActive" },
] as const;

const JOURNAL_AUDIT_DEMO = [
  { date: "2026-10-03 09:14", evenementKey: "auditLogin", acteur: "A. Dubois" },
  { date: "2026-10-02 17:40", evenementKey: "auditLibrary", acteur: "S. Okafor" },
  { date: "2026-10-01 11:02", evenementKey: "auditQuestion", acteur: "M. Nguyen" },
] as const;

export default async function AdministrationPage() {
  const tNav = await getTranslations("Nav");
  const t = await getTranslations("Administration");

  return (
    <>
      <Topbar title={tNav("administration")} description={t("topbarDescription")} />
      <main className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <DemoBanner />

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("currentOrgTitle")}</h2>
            <DemoBadge label={t("demoBadge")} />
          </div>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">{t("currentOrgValue")}</p>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("usersTitle")}</h2>
            <DemoBadge label={t("demoBadge")} />
          </div>
          <table className="mt-3 w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th className="pb-2">{t("tableColName")}</th>
                <th className="pb-2">{t("tableColRole")}</th>
                <th className="pb-2">{t("tableColStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {UTILISATEURS_DEMO.map((u) => (
                <tr key={u.nom} className="border-t border-[var(--border)] text-[var(--text-secondary)]">
                  <td className="py-2 text-[var(--text-primary)]">{u.nom}</td>
                  <td className="py-2">{t(u.roleKey)}</td>
                  <td className="py-2">{t(u.statutKey)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("rolesTitle")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {ROLES_PREPARES.map((r) => (
              <div key={r.nomKey} className="rounded-[var(--radius-md)] border border-[var(--border)] p-3">
                <p className="text-sm font-medium text-[var(--text-primary)]">{t(r.nomKey)}</p>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{t(r.descriptionKey)}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("modelsTitle")}</h2>
            <span className="text-xs text-[var(--text-muted)]">{t("modelsRealData")}</span>
          </div>
          <ul className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
            {MODELES_AUTORISES_DEMO.map((m) => (
              <li key={m.nom} className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border)] px-3 py-2">
                <span className="text-[var(--text-primary)]">{m.nom}</span>
                <span className="text-xs">{t(m.usageKey)}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("policiesTitle")}</h2>
            <DemoBadge label={t("previewBadge")} />
          </div>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">{t("policiesDescription")}</p>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{t("auditLogTitle")}</h2>
            <DemoBadge label={t("demoBadge")} />
          </div>
          <ul className="mt-3 space-y-2 text-sm">
            {JOURNAL_AUDIT_DEMO.map((entree, i) => (
              <li key={i} className="flex items-center justify-between border-t border-[var(--border)] py-2 first:border-t-0">
                <span className="text-[var(--text-secondary)]">{t(entree.evenementKey)}</span>
                <span className="text-xs text-[var(--text-muted)]">
                  {entree.acteur} · {entree.date}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </main>
    </>
  );
}
