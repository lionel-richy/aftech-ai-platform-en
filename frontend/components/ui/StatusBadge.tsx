"use client";

import { useTranslations } from "next-intl";

import type { AnswerStatus } from "@/lib/types";

const STYLES: Record<AnswerStatus, string> = {
  COMPLETE: "text-success bg-[var(--success-bg)] border-success/30",
  PARTIAL: "text-warning bg-[var(--warning-bg)] border-warning/30",
  NOT_FOUND: "text-danger bg-[var(--danger-bg)] border-danger/30",
};

const LABEL_KEYS: Record<AnswerStatus, "statusComplete" | "statusPartial" | "statusNotFound"> = {
  COMPLETE: "statusComplete",
  PARTIAL: "statusPartial",
  NOT_FOUND: "statusNotFound",
};

export function StatusBadge({ status }: { status: AnswerStatus }) {
  const t = useTranslations("Common");
  return (
    <span
      role="status"
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${STYLES[status]}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {t(LABEL_KEYS[status])} <span className="text-[10px] opacity-70">({status})</span>
    </span>
  );
}
