"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import translations, {
  LOCALES,
  type Locale,
  type TranslationKey,
} from "./translations";

const STORAGE_KEY = "gpgpu-kb.locale.v1";
const DEFAULT_LOCALE: Locale = "en";

interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  /** False during SSR / first paint; true once we've read localStorage. */
  hydrated: boolean;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function _isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

function _interpolate(
  template: string,
  params?: Record<string, string | number>,
): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    const v = params[key];
    return v === undefined || v === null ? match : String(v);
  });
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // Always start from the default locale on the server and on first client
  // render — otherwise we'd cause a hydration mismatch when the persisted
  // locale differs. We swap to the persisted locale in a mount effect.
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [hydrated, setHydrated] = useState(false);

  // Sync the persisted locale on mount. React 19 flags setState-in-effect; the
  // canonical fix would be to load the value during render via use() / a
  // server cookie, but we intentionally render the default on the server to
  // keep markup stable, then reconcile after hydration.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (_isLocale(stored)) setLocaleState(stored);
    } catch {
      // localStorage unavailable (private mode, quota) — fall back silently.
    }
    setHydrated(true);
  }, []);

  // Keep <html lang="..."> in sync so screen readers, browser translation
  // and CSS `:lang()` selectors all see the right value.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Persistence is best-effort; silently swallow quota / private-mode
      // failures so the UI still updates.
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>) => {
      const dict = translations[locale] ?? translations[DEFAULT_LOCALE];
      const template = (dict as Record<string, string>)[key] ?? key;
      return _interpolate(template, params);
    },
    [locale],
  );

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t, hydrated }),
    [locale, setLocale, t, hydrated],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale() must be used inside <LocaleProvider>");
  return ctx;
}

export function useT() {
  return useLocale().t;
}
