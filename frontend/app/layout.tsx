import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";
import "./globals.css";

import { Sidebar } from "@/components/layout/Sidebar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// The language preference (cookie "locale", read via getLocale()) must be
// known for EVERY request — <html lang> can't be static once the interface
// language is dynamic. Applies to every route (layout root), including
// /_not-found.
export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("RootLayout");
  return { title: t("title"), description: t("description") };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();

  return (
    <html
      lang={locale}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex h-full min-h-full">
        <NextIntlClientProvider>
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-y-auto">{children}</div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
