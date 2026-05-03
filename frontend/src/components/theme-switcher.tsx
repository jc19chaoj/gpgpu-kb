"use client";

import { Sun, Moon } from "lucide-react";
import { THEMES, useTheme, type Theme } from "@/lib/theme/provider";
import { useT } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const THEME_ICONS: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
};

const THEME_LABEL_KEYS: Record<Theme, "theme.light" | "theme.dark"> = {
  light: "theme.light",
  dark: "theme.dark",
};

/**
 * Segmented control theme switcher. Sun/Moon pills sit on a 1px border-track;
 * the active one slides under an amber-tinted thumb that matches the warm
 * primary color of both Cream Linen (light) and Walnut Hearth (dark) themes.
 * Mirrors LanguageSwitcher visually so the two controls compose into a
 * cohesive header cluster.
 */
export function ThemeSwitcher({ className }: { className?: string }) {
  const { theme, setTheme, hydrated } = useTheme();
  const t = useT();
  const activeIndex = THEMES.indexOf(theme);

  return (
    <div
      role="group"
      aria-label={t("theme.switch")}
      className={cn(
        "relative inline-flex items-center h-7 rounded-full",
        "border border-border bg-card/60 backdrop-blur-sm",
        "p-0.5 shadow-inner shadow-black/10 dark:shadow-black/40",
        className,
      )}
    >
      <div className="relative flex items-center">
        {/* Sliding thumb. Hidden until hydration so the SSR snapshot doesn't
            paint it under the wrong tab when localStorage disagrees with
            the default. pointer-events-none keeps clicks reaching the
            buttons underneath. */}
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute top-0 bottom-0 w-7 rounded-full",
            "transition-all duration-300 ease-out",
            "bg-gradient-to-b from-primary/30 to-primary/15",
            "ring-1 ring-primary/40",
            hydrated ? "opacity-100" : "opacity-0",
          )}
          style={{ left: `${activeIndex * 1.75}rem` }}
        />
        {THEMES.map((mode) => {
          const Icon = THEME_ICONS[mode];
          const active = theme === mode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => setTheme(mode)}
              aria-pressed={active}
              aria-label={t(THEME_LABEL_KEYS[mode])}
              title={t(THEME_LABEL_KEYS[mode])}
              className={cn(
                "relative z-10 h-6 w-7 flex items-center justify-center",
                "transition-colors duration-200",
                active
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
