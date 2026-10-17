import type { LucideIcon } from "lucide-react";
import { Blocks, LayoutDashboard, Library, MessageSquare, ShieldCheck } from "lucide-react";

export interface NavItem {
  href: string;
  labelKey: "assistant" | "bibliotheque" | "dashboard" | "administration" | "integrations";
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/assistant", labelKey: "assistant", icon: MessageSquare },
  { href: "/bibliotheque", labelKey: "bibliotheque", icon: Library },
  { href: "/dashboard", labelKey: "dashboard", icon: LayoutDashboard },
  { href: "/administration", labelKey: "administration", icon: ShieldCheck },
  { href: "/integrations", labelKey: "integrations", icon: Blocks },
];
