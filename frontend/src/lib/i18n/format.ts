import type { Locale } from "./translations";

const LOCALE_TAG: Record<Locale, string> = {
  en: "en-US",
  zh: "zh-CN",
};

export function formatDate(
  value: string | number | Date | null | undefined,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (value === null || value === undefined || value === "") return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(LOCALE_TAG[locale], options);
}

export function formatLongDate(
  value: string | number | Date | null | undefined,
  locale: Locale,
): string {
  return formatDate(value, locale, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function localeTag(locale: Locale): string {
  return LOCALE_TAG[locale];
}
