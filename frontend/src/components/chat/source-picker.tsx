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
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Pick a source for this chat</DialogTitle>
          <DialogDescription className="text-zinc-500">
            Choose a paper, blog, project, or talk. Its full content will anchor the conversation.
          </DialogDescription>
        </DialogHeader>

        <Input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by title, abstract, or summary..."
          className="bg-zinc-900 border-zinc-800 text-zinc-100"
        />

        <ScrollArea className="h-[360px] mt-2 rounded-md border border-zinc-800">
          <div className="p-2 space-y-1">
            {loading && (
              <div className="flex items-center gap-2 text-sm text-zinc-500 p-3">
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching...
              </div>
            )}
            {error && !loading && (
              <div className="text-sm text-red-400 p-3">{error}</div>
            )}
            {!loading && !error && q.trim() && results.length === 0 && (
              <div className="text-sm text-zinc-500 p-3">No matching sources.</div>
            )}
            {!loading && !error && !q.trim() && (
              <div className="text-sm text-zinc-500 p-3">Type to search the knowledge base.</div>
            )}
            {results.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePick(p)}
                className={cn(
                  "w-full text-left p-3 rounded-md transition-colors",
                  "hover:bg-zinc-800/70 focus:bg-zinc-800/70 focus:outline-none",
                )}
              >
                <div className="flex items-start gap-3">
                  <FileText className="h-4 w-4 text-emerald-400 shrink-0 mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-zinc-100 line-clamp-2">{p.title}</div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge
                        variant="outline"
                        className="text-[10px] border-zinc-700 text-zinc-400 capitalize"
                      >
                        {p.source_type}
                      </Badge>
                      {p.source_name && (
                        <span className="text-[11px] text-zinc-500">{p.source_name}</span>
                      )}
                      {(p.authors || []).length > 0 && (
                        <span className="text-[11px] text-zinc-500 truncate">
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
