"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { useTranslations } from "next-intl";

import { NAV_ITEMS } from "./nav-items";
import { BackendStatusIndicator } from "./BackendStatusIndicator";
import { OrganizationSwitcher } from "./OrganizationSwitcher";

const CLE_LOCALSTORAGE = "aftech.sidebar.repliee";

export function Sidebar() {
  const pathname = usePathname();
  const [repliee, setRepliee] = useState(false);
  const tNav = useTranslations("Nav");

  useEffect(() => {
    try {
      // One-time read of an external system (localStorage, inaccessible to
      // server rendering) after mount: a case explicitly justifying this rule.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRepliee(window.localStorage.getItem(CLE_LOCALSTORAGE) === "1");
    } catch {
      // localStorage unavailable (private browsing, etc.): keep the default value.
    }
  }, []);

  const basculer = () => {
    setRepliee((valeurPrecedente) => {
      const nouvelleValeur = !valeurPrecedente;
      try {
        window.localStorage.setItem(CLE_LOCALSTORAGE, nouvelleValeur ? "1" : "0");
      } catch {
        // Not serious: the preference is just not remembered for the next visit.
      }
      return nouvelleValeur;
    });
  };

  return (
    <aside
      className={`hidden shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-[width] duration-200 motion-reduce:transition-none md:flex ${
        repliee ? "w-[72px]" : "w-64"
      }`}
    >
      <div className="flex h-16 items-center justify-between px-4">
        {!repliee && (
          <span className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
            {tNav("brand")} <span className="text-primary">AI</span>
          </span>
        )}
        <button
          type="button"
          onClick={basculer}
          aria-label={repliee ? tNav("expand") : tNav("collapse")}
          className="rounded-md p-1.5 text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]"
        >
          {repliee ? <ChevronsRight aria-hidden className="h-4 w-4" /> : <ChevronsLeft aria-hidden className="h-4 w-4" />}
        </button>
      </div>

      <nav aria-label={tNav("mainNavLabel")} className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const actif = pathname?.startsWith(item.href);
          const Icone = item.icon;
          const label = tNav(item.labelKey);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={actif ? "page" : undefined}
              title={repliee ? label : undefined}
              className={`flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2.5 text-sm font-medium transition-colors motion-reduce:transition-none ${
                actif
                  ? "bg-primary/10 text-primary"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]"
              }`}
            >
              <Icone aria-hidden className="h-4 w-4 shrink-0" />
              {!repliee && <span>{label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-[var(--border)] p-3">
        {!repliee && <OrganizationSwitcher />}
        <BackendStatusIndicator compact={repliee} />
      </div>
    </aside>
  );
}
