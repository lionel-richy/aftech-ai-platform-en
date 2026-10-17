"use client";

// Shared states: loading, empty, error, backend unavailable.
// Explicit requirement: every data screen must know how to display these 4 cases.
import type { ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2, WifiOff } from "lucide-react";
import { useTranslations } from "next-intl";

function Conteneur({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-6 py-12 text-center"
    >
      {children}
    </div>
  );
}

export function LoadingState({ label }: { label?: string }) {
  const t = useTranslations("Common");
  return (
    <Conteneur>
      <Loader2 aria-hidden className="h-6 w-6 animate-spin text-primary motion-reduce:animate-none" />
      <p className="text-sm text-[var(--text-secondary)]">{label ?? t("loading")}</p>
    </Conteneur>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <Conteneur>
      <Inbox aria-hidden className="h-6 w-6 text-[var(--text-muted)]" />
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      {description && <p className="text-sm text-[var(--text-secondary)]">{description}</p>}
    </Conteneur>
  );
}

export function ErrorState({ title, description }: { title: string; description?: string }) {
  return (
    <Conteneur>
      <AlertTriangle aria-hidden className="h-6 w-6 text-danger" />
      <p className="text-sm font-medium text-danger">{title}</p>
      {description && <p className="text-sm text-[var(--text-secondary)]">{description}</p>}
    </Conteneur>
  );
}

export function BackendUnavailableState({ description }: { description?: string }) {
  const t = useTranslations("Common");
  return (
    <Conteneur>
      <WifiOff aria-hidden className="h-6 w-6 text-warning" />
      <p className="text-sm font-medium text-[var(--text-primary)]">{t("backendUnavailableTitle")}</p>
      <p className="text-sm text-[var(--text-secondary)]">{description ?? t("backendUnavailableDefault")}</p>
    </Conteneur>
  );
}
