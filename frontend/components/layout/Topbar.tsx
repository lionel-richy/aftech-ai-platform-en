import { UserCircle } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { LocaleSwitcher } from "./LocaleSwitcher";
import { MobileNav } from "./MobileNav";

export async function Topbar({ title, description }: { title: string; description?: string }) {
  const t = await getTranslations("Topbar");

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)]/60 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <MobileNav />
        <div>
          <h1 className="text-base font-semibold text-[var(--text-primary)]">{title}</h1>
          {description && <p className="text-xs text-[var(--text-secondary)]">{description}</p>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <LocaleSwitcher />
        <div
          className="flex items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)]"
          title={t("demoProfileTooltip")}
        >
          <UserCircle aria-hidden className="h-4 w-4" />
          <span>{t("demoProfileLabel")}</span>
        </div>
      </div>
    </header>
  );
}
