"use client";

import { Building2 } from "lucide-react";
import { useTranslations } from "next-intl";

// Prepared for future multi-tenancy: only one organization exists for now,
// so the selector is disabled rather than simulating a choice that doesn't
// really exist.
export function OrganizationSwitcher() {
  const t = useTranslations("OrganizationSwitcher");

  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      title={t("tooltip")}
      className="flex w-full items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border)] px-2.5 py-2 text-left text-xs text-[var(--text-secondary)] opacity-70"
    >
      <Building2 aria-hidden className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{t("label")}</span>
    </button>
  );
}
