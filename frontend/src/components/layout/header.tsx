"use client";

import { Menu, Cpu } from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { useT } from "@/lib/i18n/provider";

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const t = useT();
  return (
    <header className="h-12 border-b border-border flex items-center px-3 sm:px-4 bg-background/70 backdrop-blur-sm sticky top-0 z-30">
      <button
        type="button"
        onClick={onMenuClick}
        className="md:hidden -ml-1 mr-2 p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
        aria-label={t("shell.openMenu")}
      >
        <Menu className="h-5 w-5" />
      </button>
      <div className="flex items-center gap-2 md:hidden">
        <Cpu className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">{t("brand.name")}</span>
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-2 sm:gap-3">
        <ThemeSwitcher />
        <LanguageSwitcher />
      </div>
    </header>
  );
}
