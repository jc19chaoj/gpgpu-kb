"use client";

import { useState } from "react";
import {
  MessageSquarePlus,
  Trash2,
  FileText,
  X,
  History,
  PinIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/hooks/use-conversation-history";
import type { Paper } from "@/lib/types";
import { SourcePicker } from "./source-picker";

interface ChatRightSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  hydrated: boolean;
  selectedPaper: Paper | null;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onNewChat: () => void;
  onSelectPaper: (paper: Paper | null) => void;
}

function _formatTimestamp(ts: number): string {
  const diff = Date.now() - ts;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "just now";
  if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
  if (diff < day) return `${Math.floor(diff / hour)}h ago`;
  if (diff < 7 * day) return `${Math.floor(diff / day)}d ago`;
  return new Date(ts).toLocaleDateString();
}

export function ChatRightSidebar({
  conversations,
  activeId,
  hydrated,
  selectedPaper,
  onSelectConversation,
  onDeleteConversation,
  onNewChat,
  onSelectPaper,
}: ChatRightSidebarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <aside className="hidden lg:flex w-72 shrink-0 flex-col border-l border-zinc-800 bg-zinc-950/60">
      <Tabs defaultValue="history" className="flex-1 flex flex-col">
        <div className="px-3 pt-3">
          <TabsList className="w-full bg-zinc-900 border border-zinc-800">
            <TabsTrigger value="history" className="flex-1 data-[state=active]:bg-zinc-800">
              <History className="h-3.5 w-3.5 mr-1.5" />
              History
            </TabsTrigger>
            <TabsTrigger value="source" className="flex-1 data-[state=active]:bg-zinc-800">
              <PinIcon className="h-3.5 w-3.5 mr-1.5" />
              Source
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="history" className="flex-1 flex flex-col mt-2 overflow-hidden">
          <div className="px-3 pb-2">
            <Button
              onClick={onNewChat}
              size="sm"
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <MessageSquarePlus className="h-4 w-4 mr-2" />
              New chat
            </Button>
          </div>
          <ScrollArea className="flex-1 px-2 pb-3">
            {!hydrated && (
              <div className="text-xs text-zinc-600 px-2 py-3">Loading…</div>
            )}
            {hydrated && conversations.length === 0 && (
              <div className="text-xs text-zinc-500 px-2 py-3">
                No saved conversations yet. Start chatting and your sessions will appear here.
              </div>
            )}
            {hydrated && conversations.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group flex items-start gap-2 rounded-md px-2 py-2 text-sm transition-colors cursor-pointer mb-0.5",
                  c.id === activeId
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
                )}
                onClick={() => onSelectConversation(c.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{c.title}</div>
                  <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                    <span>{_formatTimestamp(c.updatedAt)}</span>
                    {c.paperTitle && (
                      <span className="flex items-center gap-1 truncate">
                        <FileText className="h-3 w-3 shrink-0" />
                        <span className="truncate">{c.paperTitle}</span>
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation(c.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 -m-1 rounded hover:bg-zinc-700/60 text-zinc-500 hover:text-zinc-100"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="source" className="flex-1 mt-2 px-3 pb-3">
          <p className="text-xs text-zinc-500 mb-3">
            Pin a single source. Its full content (PDF text for arXiv) is loaded into every
            prompt instead of relying on retrieval.
          </p>
          {selectedPaper ? (
            <div className="rounded-md border border-emerald-800/40 bg-emerald-950/20 p-3 mb-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 min-w-0">
                  <FileText className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-100 line-clamp-3">
                      {selectedPaper.title}
                    </div>
                    <div className="text-[11px] text-zinc-500 mt-1 capitalize">
                      {selectedPaper.source_type} · {selectedPaper.source_name}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelectPaper(null)}
                  className="p-1 -m-1 rounded text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800/60"
                  aria-label="Clear source"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : (
            <div className="text-xs text-zinc-600 mb-2 italic">No source pinned (using RAG).</div>
          )}
          <Button
            onClick={() => setPickerOpen(true)}
            size="sm"
            variant="outline"
            className="w-full border-zinc-700 text-zinc-100 bg-zinc-900 hover:bg-zinc-800"
          >
            {selectedPaper ? "Change source" : "Pick source"}
          </Button>
        </TabsContent>
      </Tabs>

      <SourcePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(paper) => onSelectPaper(paper)}
      />
    </aside>
  );
}
