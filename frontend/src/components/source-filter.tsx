"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Source } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

const GROUP_ORDER = ["paper", "blog", "project", "talk"] as const;
type GroupType = (typeof GROUP_ORDER)[number];

const GROUP_LABEL_KEY: Record<GroupType, TranslationKey> = {
  paper: "browse.filter.papers",
  blog: "browse.filter.blogs",
  project: "browse.filter.projects",
  talk: "browse.filter.talks",
};

export function SourceFilter({
  sources,
  selected,
  onChange,
  typeFilter,
}: {
  sources: Source[];
  selected: string[];
  onChange: (names: string[]) => void;
  typeFilter: string; // "" = All
}) {
  const t = useT();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const grouped = GROUP_ORDER.map((type) => ({
    type,
    items: sources.filter((s) => s.type === type),
  })).filter((g) => g.items.length > 0);

  // Decision 5: when type filter is active, render only that group.
  const visibleGroups = typeFilter
    ? grouped.filter((g) => g.type === typeFilter)
    : grouped;

  if (visibleGroups.length === 0) return null;

  const toggle = (name: string) => {
    onChange(
      selected.includes(name)
        ? selected.filter((n) => n !== name)
        : [...selected, name],
    );
  };

  return (
    <div className="space-y-2" data-testid="source-filter">
      {visibleGroups.map((group) => {
        const isCollapsed = collapsed[group.type] ?? false;
        const labelKey = GROUP_LABEL_KEY[group.type];
        const ariaKey: TranslationKey = isCollapsed
          ? "browse.filter.sources.expand"
          : "browse.filter.sources.collapse";
        return (
          <div key={group.type} className="space-y-1">
            <button
              type="button"
              onClick={() =>
                setCollapsed({ ...collapsed, [group.type]: !isCollapsed })
              }
              aria-label={t(ariaKey)}
              aria-expanded={!isCollapsed}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform ${
                  isCollapsed ? "" : "rotate-90"
                }`}
              />
              {t(labelKey)}
              <span className="text-[10px] opacity-60">
                ({group.items.length})
              </span>
            </button>
            {!isCollapsed && (
              <div className="flex flex-wrap gap-1 pl-4">
                {group.items.map((s) => (
                  <Badge
                    key={s.name}
                    variant={selected.includes(s.name) ? "default" : "outline"}
                    className="cursor-pointer text-[10px] gap-1"
                    onClick={() => toggle(s.name)}
                    data-testid={`source-tag-${s.name}`}
                    data-selected={selected.includes(s.name) ? "true" : "false"}
                  >
                    {s.name}
                    <span className="opacity-60">·{s.count}</span>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
