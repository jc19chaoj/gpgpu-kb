"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Cpu, User, FileText, Loader2, PinIcon, Square } from "lucide-react";
import { chatStream, getPaper } from "@/lib/api";
import type { ChatMessage, Paper } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatRightSidebar } from "@/components/chat/chat-right-sidebar";
import { useConversationHistory } from "@/hooks/use-conversation-history";
import { useT } from "@/lib/i18n/provider";

interface DisplayMessage extends ChatMessage {
  sources?: Paper[];
  /** transient: error state, not persisted to history */
  error?: boolean;
  /** transient: actively streaming tokens; placeholder shown if content empty */
  streaming?: boolean;
  /** transient: i18n welcome card; content is resolved at render-time from t() */
  welcome?: boolean;
}

// Welcome card: kept as a sentinel object whose `content` is overridden at
// render time via t("chat.welcome"). The `welcome` flag is what
// _stripDisplay uses to exclude it from history (rather than reference
// equality, which would break when the locale switch rebuilds it).
const WELCOME: DisplayMessage = {
  role: "assistant",
  content: "",
  welcome: true,
};

function _stripDisplay(messages: DisplayMessage[]): ChatMessage[] {
  // Persist & send only the role/content fields. `sources` is renderer-only;
  // `error`, `streaming` and `welcome` are transient. Drop the welcome card
  // — it's the assistant's intro, not part of the actual chat history.
  return messages
    .filter((m) => !m.welcome && !m.error && !m.streaming)
    .map(({ role, content }) => ({ role, content }));
}

function ChatContent() {
  const history = useConversationHistory();
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useT();
  const [messages, setMessages] = useState<DisplayMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Tracks the paperId we've already auto-pinned so React 19's strict-mode
  // double-effect (and any back/forward navigation) doesn't open a fresh
  // conversation twice for the same `?paperId=` deep link.
  const pinnedPaperIdRef = useRef<number | null>(null);
  // In-flight stream so we can abort on Stop, conversation switch, new
  // chat, deep-link change, or component unmount.
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight stream when the page unmounts (route change, tab
  // close). Without this the fetch would keep tokens flowing into a
  // setMessages on a stale component.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // When the user picks a saved conversation from the sidebar, hydrate the
  // local message stream from its persisted turns. We avoid re-deriving on
  // every render by gating on activeId.
  useEffect(() => {
    if (!history.active) return;
    // Switching conversations mid-stream would have the in-flight tokens
    // clobber the newly hydrated messages. Cancel first.
    abortRef.current?.abort();
    setMessages([WELCOME, ...history.active.messages.map((m) => ({ ...m }))]);
    // Restore the pinned source by id alone — we only stored the title,
    // so leaving the rest of Paper fields blank is fine for display, but
    // we need a `Paper`-shaped object. Use a minimal shape with the fields
    // the sidebar reads.
    if (history.active.paperId !== undefined && history.active.paperTitle) {
      setSelectedPaper((prev) =>
        prev?.id === history.active!.paperId
          ? prev
          : ({
              id: history.active!.paperId!,
              title: history.active!.paperTitle ?? "",
              authors: [],
              organizations: [],
              abstract: "",
              url: "",
              pdf_url: "",
              source_type: "paper",
              source_name: "",
              published_date: null,
              ingested_date: "",
              categories: [],
              venue: "",
              citation_count: 0,
              summary: "",
              originality_score: 0,
              impact_score: 0,
              impact_rationale: "",
              quality_score: 0,
              relevance_score: 0,
              score_rationale: "",
            } as Paper),
      );
    } else {
      setSelectedPaper(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.activeId]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Deep-link from the paper detail page: `/chat?paperId=123` opens a fresh
  // source-anchored conversation. We strip the query string immediately so
  // back/forward and refreshes don't keep re-pinning, and dedupe via
  // pinnedPaperIdRef in case React 19 fires the effect twice on mount.
  useEffect(() => {
    const raw = searchParams.get("paperId");
    if (!raw) return;
    const id = Number(raw);
    if (!Number.isInteger(id) || id <= 0) {
      router.replace("/chat");
      return;
    }
    if (pinnedPaperIdRef.current === id) return;
    pinnedPaperIdRef.current = id;

    let cancelled = false;
    (async () => {
      try {
        const paper = await getPaper(id);
        if (cancelled) return;
        // Strip the query only after the fetch succeeds — on 404 the URL
        // stays so the user can see the broken deep link instead of landing
        // on a clean /chat with no feedback.
        router.replace("/chat");
        history.startNew({ paperId: paper.id, paperTitle: paper.title });
        setSelectedPaper(paper);
        setMessages([WELCOME]);
      } catch {
        // Silent fallback to a normal RAG chat — matches the page's existing
        // pattern of swallowing backend errors rather than surfacing them.
      }
    })();
    return () => {
      cancelled = true;
    };
    // history & router identity changes shouldn't re-trigger this; only the
    // URL param matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleNewChat = () => {
    abortRef.current?.abort();
    setMessages([WELCOME]);
    setSelectedPaper(null);
    history.startNew();
  };

  const handlePickSource = (paper: Paper | null) => {
    setSelectedPaper(paper);
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const query = input.trim();
    setInput("");

    const userMsg: DisplayMessage = { role: "user", content: query };
    const placeholder: DisplayMessage = { role: "assistant", content: "", streaming: true };
    // Snapshot of prior turns BEFORE the new user/placeholder are appended;
    // this is what the backend should see as `history`.
    const priorTurns = _stripDisplay(messages);
    setMessages([...messages, userMsg, placeholder]);
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    let accumulated = "";
    let streamSources: Paper[] | undefined;
    let errored = false;
    let aborted = false;

    try {
      for await (const ev of chatStream(
        {
          query,
          top_k: 5,
          paper_id: selectedPaper?.id,
          history: priorTurns.length > 0 ? priorTurns : undefined,
        },
        { signal: controller.signal },
      )) {
        if (ev.type === "sources") {
          streamSources = ev.sources;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last?.streaming) return prev;
            return [...prev.slice(0, -1), { ...last, sources: streamSources }];
          });
        } else if (ev.type === "token") {
          accumulated += ev.content;
          // Capture the running total in a local so the functional updater
          // reads the up-to-date value rather than the closure snapshot.
          const snapshot = accumulated;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last?.streaming) return prev;
            return [...prev.slice(0, -1), { ...last, content: snapshot }];
          });
        } else if (ev.type === "error") {
          errored = true;
        } else if (ev.type === "done") {
          break;
        }
      }
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        aborted = true;
      } else {
        errored = true;
      }
    } finally {
      // Clear ref only if it still points at our controller — a newer send
      // may have replaced it after we started.
      if (abortRef.current === controller) abortRef.current = null;
      setLoading(false);

      // Finalize the placeholder. Three outcomes share this path:
      //   - clean done: replace with accumulated content (or placeholder)
      //   - aborted:    keep partial content (matches ChatGPT behavior)
      //   - errored:    show error bubble; don't persist
      const showError = errored && !accumulated;
      const finalContent = showError
        ? t("chat.error.generic")
        : accumulated || t("chat.empty");

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last?.streaming) return prev;
        return [
          ...prev.slice(0, -1),
          {
            role: "assistant",
            content: finalContent,
            sources: showError ? undefined : streamSources,
            streaming: false,
            error: showError,
          },
        ];
      });

      // Persist on success or partial-but-non-empty abort. Skip on pure
      // error or fully-empty abort so we don't pollute history with junk.
      //
      // Use `priorTurns` (the snapshot taken at send-start) rather than
      // _stripDisplay(messages): the closure's `messages` is stale, and if
      // the user switched conversations mid-stream it would now reference
      // the *new* conversation's history — leaking turns across sessions.
      if (!showError && (accumulated || !aborted)) {
        const persisted: ChatMessage[] = [
          ...priorTurns,
          { role: "user", content: query },
          { role: "assistant", content: finalContent },
        ];
        history.saveActive(persisted, {
          paperId: selectedPaper?.id,
          paperTitle: selectedPaper?.title,
        });
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Skip while an IME (Chinese/Japanese/Korean) is composing — pressing Enter
    // to pick a candidate would otherwise submit a half-typed message.
    // keyCode 229 covers older Safari where isComposing isn't reliably set.
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const sourceBanner = useMemo(() => {
    if (!selectedPaper) return null;
    return (
      <div className="mx-4 sm:mx-6 mt-3 mb-1 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 flex items-center gap-2 text-xs text-primary">
        <PinIcon className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">
          {t("chat.banner.anchored")}{" "}
          <span className="font-medium">{selectedPaper.title}</span>
        </span>
      </div>
    );
  }, [selectedPaper, t]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 flex flex-col max-w-3xl w-full mx-auto">
          {sourceBanner}
          <ScrollArea className="flex-1 px-4 sm:px-6">
            <div className="space-y-4 py-4">
              {messages.map((msg, i) => {
                // The welcome card's content is resolved at render-time so
                // it tracks the active locale without rewriting the messages
                // array on language switch.
                const content = msg.welcome ? t("chat.welcome") : msg.content;
                return (
                  <div key={i} className="flex gap-3">
                    <div className="shrink-0 mt-1">
                      {msg.role === "assistant" ? (
                        <Cpu className={msg.error ? "h-5 w-5 text-destructive" : "h-5 w-5 text-primary"} />
                      ) : (
                        // User stays in a cool blue so the two roles remain
                        // visually distinguishable against a warm theme.
                        <User className="h-5 w-5 text-sky-500 dark:text-sky-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-muted-foreground mb-1">
                        {msg.role === "assistant" ? t("chat.role.assistant") : t("chat.role.you")}
                      </div>
                      <div className="prose prose-sm dark:prose-invert max-w-none text-foreground/85">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                      </div>
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-border">
                          <p className="text-xs text-muted-foreground mb-2">{t("chat.sources")}</p>
                          <div className="flex flex-wrap gap-2">
                            {msg.sources.map((s) => (
                              <Link key={s.id} href={`/paper/${s.id}`}>
                                <Badge
                                  variant="outline"
                                  className="cursor-pointer hover:bg-muted text-xs border-border text-muted-foreground"
                                >
                                  <FileText className="h-3 w-3 mr-1" />
                                  {s.title.slice(0, 60)}
                                  {s.title.length > 60 ? "..." : ""}
                                </Badge>
                              </Link>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {/* Pre-token spinner: only while we're waiting on the first
                  streamed chunk. Once tokens start flowing the streaming
                  placeholder bubble already gives live feedback. */}
              {loading
                && messages[messages.length - 1]?.streaming
                && !messages[messages.length - 1]?.content && (
                <div className="flex gap-3">
                  <Loader2 className="h-5 w-5 text-primary animate-spin shrink-0 mt-1" />
                  <div className="text-sm text-muted-foreground">
                    {selectedPaper ? t("chat.loading.reading") : t("chat.loading.search")}
                  </div>
                </div>
              )}
              <div ref={scrollRef} />
            </div>
          </ScrollArea>

          <div className="border-t border-border p-3 sm:p-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] bg-background/80 backdrop-blur-sm">
            <div className="flex items-center gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  selectedPaper
                    ? t("chat.placeholder.anchored", {
                        title: selectedPaper.title.slice(0, 40),
                      })
                    : t("chat.placeholder.default")
                }
                enterKeyHint="send"
                className="flex-1 bg-card border-border text-base sm:text-sm h-10 sm:h-9"
                disabled={loading}
              />
              {loading ? (
                <Button
                  type="button"
                  size="icon"
                  aria-label={t("chat.stop")}
                  className="bg-destructive hover:bg-destructive/90 text-white h-10 w-10 sm:h-9 sm:w-9 shrink-0"
                  onClick={handleStop}
                >
                  <Square className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  aria-label={t("chat.send")}
                  disabled={!input.trim()}
                  className="bg-primary hover:bg-primary/90 text-primary-foreground h-10 w-10 sm:h-9 sm:w-9 shrink-0"
                  onClick={handleSend}
                >
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground/70 mt-2 hidden sm:block">
              {selectedPaper
                ? t("chat.disclaimer.anchored")
                : t("chat.disclaimer.default")}
            </p>
          </div>
        </div>
      </div>

      <ChatRightSidebar
        conversations={history.conversations}
        activeId={history.activeId}
        hydrated={history.hydrated}
        selectedPaper={selectedPaper}
        onSelectConversation={history.selectConversation}
        onDeleteConversation={history.deleteConversation}
        onNewChat={handleNewChat}
        onSelectPaper={handlePickSource}
      />
    </div>
  );
}

export default function ChatPage() {
  // Suspense is required by Next 16 around any client tree that calls
  // useSearchParams (we read `?paperId=` for source-anchored deep links).
  return (
    <Suspense fallback={null}>
      <ChatContent />
    </Suspense>
  );
}
