import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/layout/app-shell";
import { LocaleProvider } from "@/lib/i18n/provider";
import { ThemeProvider } from "@/lib/theme/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "GPGPU Knowledge Base",
  description: "Curated research knowledge base for GPGPU chip architecture",
};

// Dual-mode address-bar tint: matches Cream Linen / Walnut Hearth backgrounds
// per OS preference. Note: this honors `prefers-color-scheme` (an OS signal),
// independent of our class-based runtime toggle in <html>.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbf7ee" },
    { media: "(prefers-color-scheme: dark)", color: "#251c14" },
  ],
};

// Synchronous pre-paint script that toggles the `dark` class on <html>
// before the body renders, eliminating any flash-of-wrong-theme on first
// paint. The storage key MUST stay in sync with THEME_STORAGE_KEY in
// lib/theme/provider.tsx — change one, change both.
//
// We default to dark (matches DEFAULT_THEME). Any error reading
// localStorage falls back to dark too, so we never paint the body without
// a class set.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("gpgpu-kb.theme.v1");var d=document.documentElement;if(t==="light"){d.classList.remove("dark");}else{d.classList.add("dark");}}catch(_){document.documentElement.classList.add("dark");}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The server always renders className="dark" (matches DEFAULT_THEME), then
  // the inline <head> script swaps to the persisted choice synchronously
  // before paint. LocaleProvider's effect swaps document.documentElement.lang
  // similarly. suppressHydrationWarning silences the intentional class /
  // lang mismatch React would otherwise complain about.
  return (
    <html lang="en" className="h-full antialiased dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground font-sans">
        <ThemeProvider>
          <LocaleProvider>
            <AppShell>{children}</AppShell>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
