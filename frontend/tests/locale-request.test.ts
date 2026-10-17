import { describe, expect, it } from "vitest";

import { resoudreLocaleDepuisCookie } from "@/i18n/config";

// resoudreLocaleDepuisCookie is the logic used by i18n/request.ts (read by
// getLocale() on the server, then by <html lang={locale}> in
// app/layout.tsx) — tested here in isolation, without next/headers or
// next-intl/server: those modules expose a "react-server" export condition
// that Vitest (outside the Next.js runtime) cannot satisfy.
// Covers: language preference persisted via cookie, and the HTML lang
// attribute updated dynamically (since the same locale value drives both).
describe("resoudreLocaleDepuisCookie", () => {
  it("uses the cookie's locale when it is valid ('de')", () => {
    expect(resoudreLocaleDepuisCookie("de")).toBe("de");
  });

  it("uses the cookie's locale when it is valid ('en')", () => {
    expect(resoudreLocaleDepuisCookie("en")).toBe("en");
  });

  it("falls back to 'en' by default if the cookie is absent", () => {
    expect(resoudreLocaleDepuisCookie(undefined)).toBe("en");
  });

  it("falls back to 'en' by default if the cookie contains an invalid value", () => {
    expect(resoudreLocaleDepuisCookie("es")).toBe("en");
  });
});
