"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";

export function StatTile({
  label,
  value,
  icon,
  unavailableReason,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  /** If provided, shows "Not available" instead of `value` — never a made-up number. */
  unavailableReason?: string;
}) {
  const t = useTranslations("Dashboard");

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">{label}</span>
        {icon && <span className="text-primary">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
        {unavailableReason ? (
          <span className="text-base font-normal text-[var(--text-muted)]">{t("notAvailable")}</span>
        ) : (
          value
        )}
      </div>
      {unavailableReason && <p className="mt-1 text-xs text-[var(--text-muted)]">{unavailableReason}</p>}
    </div>
  );
}
