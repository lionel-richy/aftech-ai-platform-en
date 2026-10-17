import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/actions/locale", () => ({ definirLocale: vi.fn() }));

import { definirLocale } from "@/lib/actions/locale";
import { LocaleSwitcher } from "@/components/layout/LocaleSwitcher";
import { renderAvecIntl } from "./test-utils";

describe("LocaleSwitcher", () => {
  it("offers the 3 languages (fr/en/de) in their native name", () => {
    renderAvecIntl(<LocaleSwitcher />);
    expect(screen.getByRole("option", { name: "Français" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Deutsch" })).toBeInTheDocument();
  });

  it("shows the current locale as selected", () => {
    renderAvecIntl(<LocaleSwitcher />, { locale: "de" });
    expect(screen.getByRole("combobox")).toHaveValue("de");
  });

  it("calls the definirLocale Server Action when the language changes", () => {
    renderAvecIntl(<LocaleSwitcher />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(definirLocale).toHaveBeenCalledWith("en");
  });

  it("has an accessible label (requirement: accessible language switcher)", () => {
    renderAvecIntl(<LocaleSwitcher />);
    expect(screen.getByRole("combobox", { name: "Langue de l'interface" })).toBeInTheDocument();
  });
});
