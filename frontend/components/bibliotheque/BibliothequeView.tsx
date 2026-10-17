"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutGrid, List, Search } from "lucide-react";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/StateViews";
import type { DocumentItem } from "@/lib/types";
import { AjouterDocumentButton } from "./AjouterDocumentButton";
import { DocumentCard } from "./DocumentCard";

type Tri = "nom" | "pages" | "passages";

export function BibliothequeView({ documents }: { documents: DocumentItem[] }) {
  const [recherche, setRecherche] = useState("");
  const [tri, setTri] = useState<Tri>("nom");
  const [vue, setVue] = useState<"grille" | "liste">("grille");
  const t = useTranslations("Bibliotheque");
  const router = useRouter();

  const documentsFiltres = useMemo(() => {
    const filtre = documents.filter((d) => d.nom_fichier.toLowerCase().includes(recherche.toLowerCase()));
    const copie = [...filtre];
    copie.sort((a, b) => {
      if (tri === "pages") return b.pages - a.pages;
      if (tri === "passages") return b.passages - a.passages;
      return a.nom_fichier.localeCompare(b.nom_fichier);
    });
    return copie;
  }, [documents, recherche, tri]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="search"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchAriaLabel")}
            className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          {t("sortBy")}
          <select
            value={tri}
            onChange={(e) => setTri(e.target.value as Tri)}
            className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none"
          >
            <option value="nom">{t("sortName")}</option>
            <option value="pages">{t("sortPages")}</option>
            <option value="passages">{t("sortPassages")}</option>
          </select>
        </label>

        <div className="flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--border)] p-1">
          <button
            type="button"
            onClick={() => setVue("grille")}
            aria-pressed={vue === "grille"}
            aria-label={t("gridView")}
            className={`rounded p-1.5 ${vue === "grille" ? "bg-primary/10 text-primary" : "text-[var(--text-muted)]"}`}
          >
            <LayoutGrid aria-hidden className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setVue("liste")}
            aria-pressed={vue === "liste"}
            aria-label={t("listView")}
            className={`rounded p-1.5 ${vue === "liste" ? "bg-primary/10 text-primary" : "text-[var(--text-muted)]"}`}
          >
            <List aria-hidden className="h-4 w-4" />
          </button>
        </div>

        <AjouterDocumentButton onDocumentAjoute={() => router.refresh()} />
      </div>

      {documentsFiltres.length === 0 ? (
        <EmptyState title={t("emptyFilteredTitle")} description={t("emptyFilteredDescription")} />
      ) : (
        <div className={vue === "grille" ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3" : "flex flex-col gap-3"}>
          {documentsFiltres.map((document) => (
            <DocumentCard
              key={document.id ?? document.nom_fichier}
              document={document}
              onSupprime={() => router.refresh()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
