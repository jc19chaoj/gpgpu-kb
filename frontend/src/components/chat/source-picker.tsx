"use client";

import { useEffect, useRef, useState } from "react";
import { searchPapers } from "@/lib/api";
import type { Paper } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Loader2, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";

interface SourcePickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (paper: Paper) => void;
}

const SEARCH_DEBOUNCE_MS = 300;

export function SourcePicker({ open, onOpenChange, onSelect }: SourcePickerProps) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const t = useT();

  // Reset on open so a stale query doesn't persist between sessions.
  useEffect(() => {
    if (open) {
      setQ("");
      setResults([]);
      setError(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const query = q.trim();
    if (!query) {
      setResults([]);
      setLoading(false);
      return;
    }

    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    const handle = window.setTimeout(async () => {
      try {
        const res = await searchPapers(query, { page_size: 12, semantic: false });
        // Late-arriving response from a stale query — discard.
        if (seq !== requestSeq.current) return;
        setResults(res.papers);
      } catch (e) {
        if (seq !== requestSeq.current) return;
        setError(e instanceof Error ? e.message : "Search failed");
        setResults([]);
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [q, open]);

  const handlePick = (paper: Paper) => {
    onSelect(paper);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background border-border text-foreground max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-foreground">{t("picker.title")}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t("picker.description")}
          </DialogDescription>
        </DialogHeader>

        <Input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("picker.placeholder")}
          className="bg-card border-border text-foreground"
        />

        <ScrollArea className="h-[360px] mt-2 rounded-md border border-border">
          <div className="p-2 space-y-1">
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground p-3">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("picker.searching")}
              </div>
            )}
            {error && !loading && (
              <div className="text-sm text-destructive p-3">{error}</div>
            )}
            {!loading && !error && q.trim() && results.length === 0 && (
              <div className="text-sm text-muted-foreground p-3">{t("picker.empty")}</div>
            )}
            {!loading && !error && !q.trim() && (
              <div className="text-sm text-muted-foreground p-3">{t("picker.hint")}</div>
            )}
            {results.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePick(p)}
                className={cn(
                  "w-full text-left p-3 rounded-md transition-colors",
                  "hover:bg-muted/70 focus:bg-muted/70 focus:outline-none",
                )}
              >
                <div className="flex items-start gap-3">
                  <FileText className="h-4 w-4 text-primary shrink-0 mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-foreground line-clamp-2">{p.title}</div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge
                        variant="outline"
                        className="text-[10px] border-border text-muted-foreground capitalize"
                      >
                        {p.source_type}
                      </Badge>
                      {p.source_name && (
                        <span className="text-[11px] text-muted-foreground">{p.source_name}</span>
                      )}
                      {(p.authors || []).length > 0 && (
                        <span className="text-[11px] text-muted-foreground truncate">
                          {(p.authors || []).slice(0, 3).join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
