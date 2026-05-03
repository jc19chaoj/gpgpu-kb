"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type Theme = "light" | "dark";

export const THEMES: readonly Theme[] = ["light", "dark"] as const;

// Storage key kept in sync with the FOUC-prevention inline script in
// app/layout.tsx — change one, change both.
export const THEME_STORAGE_KEY = "gpgpu-kb.theme.v1";

// SSR / first-paint default. The synchronous <head> script will swap to the
// persisted choice before the body paints, so this only matters for the
// brief pre-hydration moment on first ever visit.
export const DEFAULT_THEME: Theme = "dark";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (next: Theme) => void;
  toggle: () => void;
  /** False during SSR / first paint; true once we've reconciled with localStorage. */
  hydrated: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function _isTheme(v: unknown): v is Theme {
  return v === "light" || v === "dark";
}

/**
 * Theme provider. Mirrors the LocaleProvider pattern: server always renders
 * the default, then a mount effect reconciles with the persisted value. The
 * inline FOUC script in layout.tsx sets the <html> class *before* React
 * mounts so painted background never flickers.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(DEFAULT_THEME);
  const [hydrated, setHydrated] = useState(false);

  // Reconcile in-memory state with the value the FOUC script already
  // applied. We can't read it during render (SSR has no localStorage), so
  // we accept one re-render after mount. React 19 flags setState-in-effect;
  // canonical fix would be to thread the value through a server cookie, but
  // we already keep markup stable by using the default during SSR.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (_isTheme(stored)) setThemeState(stored);
    } catch {
      // localStorage unavailable (private mode, quota) — silently keep default.
    }
    setHydrated(true);
  }, []);

  // Keep the <html> class in sync with the in-memory theme so Tailwind's
  // `dark:` variant resolves correctly. The FOUC script handles the very
  // first paint; this effect handles every runtime toggle thereafter.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // best-effort persistence
    }
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // best-effort persistence
      }
      return next;
    });
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, toggle, hydrated }),
    [theme, setTheme, toggle, hydrated],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme() must be used inside <ThemeProvider>");
  return ctx;
}
