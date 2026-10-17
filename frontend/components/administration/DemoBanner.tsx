import { FlaskConical } from "lucide-react";
import { getTranslations } from "next-intl/server";

export async function DemoBanner() {
  const t = await getTranslations("Administration");

  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-accent/30 bg-accent/10 p-4"
    >
      <FlaskConical aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
      <div>
        <p className="text-sm font-semibold text-accent">{t("demoModeTitle")}</p>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("demoModeDescription")}</p>
      </div>
    </div>
  );
}
