"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { useTranslations } from "next-intl";

import { NAV_ITEMS } from "./nav-items";

export function MobileNav() {
  const [ouvert, setOuvert] = useState(false);
  const pathname = usePathname();
  const tNav = useTranslations("Nav");

  return (
    <div className="md:hidden">
      <button
        type="button"
        onClick={() => setOuvert(true)}
        aria-label={tNav("openMenu")}
        aria-expanded={ouvert}
        className="rounded-md p-2 text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]"
      >
        <Menu aria-hidden className="h-5 w-5" />
      </button>

      {ouvert && (
        <div className="fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setOuvert(false)}
            aria-hidden="true"
          />
          <nav
            aria-label={tNav("mobileNavLabel")}
            className="relative z-10 flex h-full w-72 flex-col gap-1 bg-[var(--surface)] p-4"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="text-lg font-semibold text-[var(--text-primary)]">
                {tNav("brand")} <span className="text-primary">AI</span>
              </span>
              <button
                type="button"
                onClick={() => setOuvert(false)}
                aria-label={tNav("closeMenu")}
                className="rounded-md p-1.5 text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]"
              >
                <X aria-hidden className="h-5 w-5" />
              </button>
            </div>
            {NAV_ITEMS.map((item) => {
              const actif = pathname?.startsWith(item.href);
              const Icone = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOuvert(false)}
                  aria-current={actif ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2.5 text-sm font-medium ${
                    actif ? "bg-primary/10 text-primary" : "text-[var(--text-secondary)]"
                  }`}
                >
                  <Icone aria-hidden className="h-4 w-4" />
                  <span>{tNav(item.labelKey)}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      )}
    </div>
  );
}
