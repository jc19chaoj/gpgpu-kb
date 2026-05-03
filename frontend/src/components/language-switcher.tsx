"use client";

import { useLocale } from "@/lib/i18n/provider";
import {
  LOCALES,
  LOCALE_LABELS,
  LOCALE_FULL_LABELS,
  type Locale,
} from "@/lib/i18n/translations";
import { Languages } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Segmented control language switcher. Two pills (`EN` / `中`) sit on a
 * 1px border-track; the active one slides under a primary-tinted thumb.
 * Mirrors ThemeSwitcher visually so they compose as a header cluster.
 */
export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();
  const activeIndex = LOCALES.indexOf(locale);

  return (
    <div
      role="group"
      aria-label={t("lang.switch")}
      className={cn(
        "relative inline-flex items-center h-7 rounded-full",
        "border border-border bg-card/60 backdrop-blur-sm",
        "p-0.5 shadow-inner shadow-black/10 dark:shadow-black/40",
        className,
      )}
    >
      <Languages
        aria-hidden
        className="h-3 w-3 text-muted-foreground/70 ml-1.5 mr-1 shrink-0"
      />
      <div className="relative flex items-center">
        {/* sliding thumb — pointer-events-none so it never captures
            clicks meant for the buttons underneath */}
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute top-0 bottom-0 w-7 rounded-full transition-all duration-300 ease-out",
            "bg-gradient-to-b from-primary/30 to-primary/15",
            "ring-1 ring-primary/40",
          )}
          style={{ left: `${activeIndex * 1.75}rem` }}
        />
        {LOCALES.map((code: Locale) => {
          const active = locale === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => setLocale(code)}
              aria-pressed={active}
              aria-label={code === "en" ? t("lang.english") : t("lang.chinese")}
              title={LOCALE_FULL_LABELS[code]}
              className={cn(
                "relative z-10 h-6 w-7 flex items-center justify-center",
                "text-[11px] font-semibold tracking-wide select-none",
                "transition-colors duration-200",
                active
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {LOCALE_LABELS[code]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
