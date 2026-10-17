"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslations } from "next-intl";

import type { MetricsResponse } from "@/lib/types";

export function StatusBreakdownChart({ metrics }: { metrics: MetricsResponse }) {
  const t = useTranslations("Dashboard");
  const tCommon = useTranslations("Common");

  const donnees = [
    { statut: tCommon("statusComplete"), valeur: metrics.status_complete, couleur: "var(--success)" },
    { statut: tCommon("statusPartial"), valeur: metrics.status_partial, couleur: "var(--warning)" },
    { statut: tCommon("statusNotFound"), valeur: metrics.status_not_found, couleur: "var(--danger)" },
  ];

  if (metrics.requests_total === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">{t("statusBreakdownEmpty")}</p>;
  }

  return (
    <div className="h-56 w-full" role="img" aria-label={t("statusBreakdownAriaLabel")}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={donnees} layout="vertical" margin={{ left: 16, right: 16 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" stroke="var(--text-muted)" fontSize={12} allowDecimals={false} />
          <YAxis type="category" dataKey="statut" stroke="var(--text-muted)" fontSize={12} width={80} />
          <Tooltip
            contentStyle={{ background: "var(--surface-elevated)", border: "1px solid var(--border)", borderRadius: 8 }}
            labelStyle={{ color: "var(--text-primary)" }}
          />
          <Bar dataKey="valeur" radius={[0, 6, 6, 0]}>
            {donnees.map((d) => (
              <Cell key={d.statut} fill={d.couleur} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
