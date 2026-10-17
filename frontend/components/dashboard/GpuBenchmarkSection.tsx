"use client";

import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/StateViews";
import type { ComparisonGpu } from "@/lib/gpuBenchmark";

export function GpuBenchmarkSection({ comparaison }: { comparaison: ComparisonGpu }) {
  const t = useTranslations("Dashboard");

  if (!comparaison.executed) {
    return (
      <EmptyState
        title={t("benchmarkNotExecutedTitle")}
        description={t("benchmarkNotExecutedDescription")}
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            <th className="pb-2 pr-4">{t("benchmarkColGpu")}</th>
            <th className="pb-2 pr-4">{t("benchmarkColVram")}</th>
            <th className="pb-2 pr-4">{t("benchmarkColLatency")}</th>
            <th className="pb-2 pr-4">{t("benchmarkColTokensPerSec")}</th>
            <th className="pb-2 pr-4">{t("benchmarkColPeakMemory")}</th>
            <th className="pb-2">{t("benchmarkColErrors")}</th>
          </tr>
        </thead>
        <tbody>
          {comparaison.lignes.map((ligne) => (
            <tr key={ligne.gpu} className="border-t border-[var(--border)] text-[var(--text-primary)]">
              <td className="py-2 pr-4 font-medium">{ligne.gpu}</td>
              <td className="py-2 pr-4">{ligne.vram_totale_go ?? "—"} GB</td>
              <td className="py-2 pr-4">{ligne.temps_total_moyen_s?.toFixed(2) ?? "—"} s</td>
              <td className="py-2 pr-4">{ligne.tokens_par_seconde_moyen?.toFixed(1) ?? "—"}</td>
              <td className="py-2 pr-4">{ligne.memoire_gpu_pic_go_max ?? "—"} GB</td>
              <td className="py-2">{ligne.nb_erreurs ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-[var(--text-muted)]">{t("benchmarkRecommendationNote")}</p>
    </div>
  );
}
