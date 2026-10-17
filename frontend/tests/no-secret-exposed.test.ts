import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// STATICALLY verifies (source code) that the backend key is never exposed
// to the browser: never prefixed NEXT_PUBLIC_, never imported outside
// server routes. A stronger complementary check is to grep the production
// bundle after "next build" (see docs/FRONTEND_GUIDE.md): this test runs on
// every run, without waiting for a full build.
const RACINE = path.resolve(__dirname, "..");
const DOSSIERS_A_IGNORER = new Set(["node_modules", ".next", "tests", "test-results"]);

function listerFichiersSource(dossier: string): string[] {
  const resultats: string[] = [];
  for (const entree of readdirSync(dossier)) {
    if (DOSSIERS_A_IGNORER.has(entree)) continue;
    const cheminComplet = path.join(dossier, entree);
    const infos = statSync(cheminComplet);
    if (infos.isDirectory()) {
      resultats.push(...listerFichiersSource(cheminComplet));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entree)) {
      resultats.push(cheminComplet);
    }
  }
  return resultats;
}

describe("No backend secret exposed on the client side", () => {
  const fichiers = listerFichiersSource(RACINE);

  it("no source file references NEXT_PUBLIC_BACKEND_API_KEY", () => {
    const fichiersSuspects = fichiers.filter((f) => readFileSync(f, "utf-8").includes("NEXT_PUBLIC_BACKEND_API_KEY"));
    expect(fichiersSuspects).toEqual([]);
  });

  it("only lib/backend.ts reads process.env.BACKEND_API_KEY (never a client component)", () => {
    const fichiersUtilisantLaCle = fichiers.filter(
      (f) =>
        readFileSync(f, "utf-8").includes("process.env.BACKEND_API_KEY") &&
        !f.endsWith("backend-client.test.ts"),
    );
    const chemins = fichiersUtilisantLaCle.map((f) => path.relative(RACINE, f));
    expect(chemins).toEqual(["lib/backend.ts"]);
  });

  it("no \"use client\" component references BACKEND_API_KEY", () => {
    const fichiersSuspects = fichiers.filter((f) => {
      const contenu = readFileSync(f, "utf-8");
      return contenu.startsWith('"use client"') && contenu.includes("BACKEND_API_KEY");
    });
    expect(fichiersSuspects).toEqual([]);
  });

  it("lib/backend.ts does import 'server-only' (build-time guard rail)", () => {
    const contenu = readFileSync(path.join(RACINE, "lib", "backend.ts"), "utf-8");
    expect(contenu).toContain('import "server-only"');
  });
});
