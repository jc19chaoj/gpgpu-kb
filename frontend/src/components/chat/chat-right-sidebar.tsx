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
import { useLocale } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/i18n/format";
import type { Locale } from "@/lib/i18n/translations";

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

function _formatTimestamp(
  ts: number,
  locale: Locale,
  t: (key: Parameters<ReturnType<typeof useLocale>["t"]>[0], params?: Record<string, string | number>) => string,
): string {
  const diff = Date.now() - ts;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return t("chat.time.justNow");
  if (diff < hour) return t("chat.time.minutes", { n: Math.floor(diff / minute) });
  if (diff < day) return t("chat.time.hours", { n: Math.floor(diff / hour) });
  if (diff < 7 * day) return t("chat.time.days", { n: Math.floor(diff / day) });
  return formatDate(ts, locale);
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
  const { locale, t } = useLocale();

  return (
    <aside className="hidden lg:flex w-72 shrink-0 flex-col border-l border-border bg-sidebar/60">
      <Tabs defaultValue="history" className="flex-1 flex flex-col">
        <div className="px-3 pt-3">
          <TabsList className="w-full bg-card border border-border">
            <TabsTrigger value="history" className="flex-1 data-[state=active]:bg-muted">
              <History className="h-3.5 w-3.5 mr-1.5" />
              {t("chat.tabs.history")}
            </TabsTrigger>
            <TabsTrigger value="source" className="flex-1 data-[state=active]:bg-muted">
              <PinIcon className="h-3.5 w-3.5 mr-1.5" />
              {t("chat.tabs.source")}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="history" className="flex-1 flex flex-col mt-2 overflow-hidden">
          <div className="px-3 pb-2">
            <Button
              onClick={onNewChat}
              size="sm"
              className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <MessageSquarePlus className="h-4 w-4 mr-2" />
              {t("chat.newChat")}
            </Button>
          </div>
          <ScrollArea className="flex-1 px-2 pb-3">
            {!hydrated && (
              <div className="text-xs text-muted-foreground/70 px-2 py-3">{t("chat.history.loading")}</div>
            )}
            {hydrated && conversations.length === 0 && (
              <div className="text-xs text-muted-foreground px-2 py-3">
                {t("chat.history.empty")}
              </div>
            )}
            {hydrated && conversations.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group flex items-start gap-2 rounded-md px-2 py-2 text-sm transition-colors cursor-pointer mb-0.5",
                  c.id === activeId
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
                onClick={() => onSelectConversation(c.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{c.title}</div>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span>{_formatTimestamp(c.updatedAt, locale, t)}</span>
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
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 -m-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                  aria-label={t("chat.history.delete")}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="source" className="flex-1 mt-2 px-3 pb-3">
          <p className="text-xs text-muted-foreground mb-3">
            {t("chat.source.intro")}
          </p>
          {selectedPaper ? (
            <div className="rounded-md border border-primary/30 bg-primary/10 p-3 mb-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 min-w-0">
                  <FileText className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground line-clamp-3">
                      {selectedPaper.title}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1 capitalize">
                      {selectedPaper.source_type} · {selectedPaper.source_name}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelectPaper(null)}
                  className="p-1 -m-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  aria-label={t("chat.source.clear")}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground/70 mb-2 italic">{t("chat.source.empty")}</div>
          )}
          <Button
            onClick={() => setPickerOpen(true)}
            size="sm"
            variant="outline"
            className="w-full border-border text-foreground bg-card hover:bg-muted"
          >
            {selectedPaper ? t("chat.source.change") : t("chat.source.pick")}
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
