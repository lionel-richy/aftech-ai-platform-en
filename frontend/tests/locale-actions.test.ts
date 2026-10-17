import { describe, expect, it, vi } from "vitest";

// Persisted language preference requirement: the Server Action writes a
// NON-sensitive cookie (no user data, just "fr"/"en"/"de"), later read by
// i18n/request.ts on every render — see locale-request.test.ts for the full
// loop (write -> read -> effective locale).
const cookieStoreMock = { set: vi.fn(), get: vi.fn() };
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => cookieStoreMock),
}));

describe("definirLocale (LocaleSwitcher Server Action)", () => {
  it("writes a non-sensitive 'locale' cookie for a valid language", async () => {
    const { definirLocale } = await import("@/lib/actions/locale");
    await definirLocale("de");

    expect(cookieStoreMock.set).toHaveBeenCalledWith(
      "locale",
      "de",
      expect.objectContaining({ sameSite: "lax" }),
    );
  });

  it("writes NOTHING for an invalid language (server-side defense in depth)", async () => {
    cookieStoreMock.set.mockClear();
    const { definirLocale } = await import("@/lib/actions/locale");
    // @ts-expect-error -- deliberately forcing a value outside the Locale type
    await definirLocale("es");

    expect(cookieStoreMock.set).not.toHaveBeenCalled();
  });
});
