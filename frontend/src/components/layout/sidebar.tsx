"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BookOpen, MessageCircle, Newspaper, BarChart3, Cpu, X } from "lucide-react";
import pkg from "../../../package.json";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

const navItems: { href: string; labelKey: TranslationKey; icon: typeof BookOpen }[] = [
  { href: "/", labelKey: "nav.browse", icon: BookOpen },
  { href: "/chat", labelKey: "nav.chat", icon: MessageCircle },
  { href: "/reports", labelKey: "nav.reports", icon: Newspaper },
  { href: "/stats", labelKey: "nav.stats", icon: BarChart3 },
];

interface SidebarProps {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const t = useT();

  return (
    <>
      {/* Mobile backdrop */}
      <div
        aria-hidden
        onClick={onMobileClose}
        className={cn(
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-200 md:hidden",
          mobileOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
      />

      <aside
        className={cn(
          // Mobile: fixed off-canvas drawer
          "fixed inset-y-0 left-0 z-50 w-64 max-w-[80vw] border-r border-border bg-sidebar text-sidebar-foreground flex flex-col h-dvh transform transition-transform duration-200 ease-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // Desktop: persistent rail
          "md:static md:translate-x-0 md:w-60 md:max-w-none md:shrink-0 md:z-auto"
        )}
        aria-label={t("nav.primary")}
      >
        <div className="p-4 border-b border-sidebar-border flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-primary" />
            <span className="font-semibold text-sm">{t("brand.name")}</span>
          </div>
          <button
            type="button"
            onClick={onMobileClose}
            className="md:hidden -mr-1 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            aria-label={t("shell.closeMenu")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-3 px-3 py-2.5 md:py-2 rounded-md text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-sidebar-accent/60",
                )}
              >
                {/* Subtle warm-amber rail accent on the active item — keeps
                    the sidebar palette restrained while still signaling
                    "you are here". */}
                {active && (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-primary"
                  />
                )}
                <item.icon className="h-4 w-4 shrink-0" />
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-sidebar-border">
          <span className="text-[10px] sm:text-xs text-muted-foreground tabular-nums">
            {t("shell.version")}{pkg.version}
          </span>
        </div>
      </aside>
    </>
  );
}
