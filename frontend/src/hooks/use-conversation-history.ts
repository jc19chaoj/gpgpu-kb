"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChatMessage } from "@/lib/types";

const STORAGE_KEY = "gpgpu-kb.chat.conversations.v1";
const MAX_CONVERSATIONS = 50;

export interface Conversation {
  id: string;
  title: string;
  /** Optional pinned source id (paper). When set the chat ran in source-anchored mode. */
  paperId?: number;
  paperTitle?: string;
  messages: ChatMessage[];
  /** Epoch millis of last update. */
  updatedAt: number;
}

function _safeRead(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(_isConversation);
  } catch {
    return [];
  }
}

function _isConversation(c: unknown): c is Conversation {
  if (!c || typeof c !== "object") return false;
  const r = c as Record<string, unknown>;
  return (
    typeof r.id === "string" &&
    typeof r.title === "string" &&
    Array.isArray(r.messages) &&
    typeof r.updatedAt === "number"
  );
}

function _safeWrite(list: Conversation[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_CONVERSATIONS)));
  } catch {
    // Silent: localStorage may be full or disabled. The in-memory state still
    // works for the current session.
  }
}

function _newId(): string {
  // crypto.randomUUID is widely supported in modern browsers; fall back to
  // a timestamp+random combination if not (e.g. ancient embedded WebView).
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function _deriveTitle(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "New chat";
  const text = firstUser.content.trim().replace(/\s+/g, " ");
  return text.length > 60 ? `${text.slice(0, 60)}…` : text || "New chat";
}

export interface UseConversationHistory {
  conversations: Conversation[];
  activeId: string | null;
  active: Conversation | null;
  /** Switch to an existing conversation. */
  selectConversation: (id: string) => void;
  /** Start a fresh conversation; returns its id. */
  startNew: (opts?: { paperId?: number; paperTitle?: string }) => string;
  /** Persist messages for the active conversation (creates one if none active). */
  saveActive: (messages: ChatMessage[], opts?: { paperId?: number; paperTitle?: string }) => void;
  /** Delete a conversation; if it was active, clear active. */
  deleteConversation: (id: string) => void;
  /** Wipe everything. */
  clearAll: () => void;
  /** True after the first browser-side mount; UI should avoid rendering
   *  history-driven state until then to prevent SSR/CSR mismatch. */
  hydrated: boolean;
}

export function useConversationHistory(): UseConversationHistory {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Load on mount only; the SSR pass renders an empty list to keep markup
  // identical between server and first client render.
  useEffect(() => {
    const list = _safeRead();
    list.sort((a, b) => b.updatedAt - a.updatedAt);
    setConversations(list);
    setHydrated(true);
  }, []);

  const persist = useCallback((next: Conversation[]) => {
    next.sort((a, b) => b.updatedAt - a.updatedAt);
    setConversations(next);
    _safeWrite(next);
  }, []);

  const selectConversation = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const startNew = useCallback(
    (opts?: { paperId?: number; paperTitle?: string }) => {
      const id = _newId();
      const conv: Conversation = {
        id,
        title: "New chat",
        paperId: opts?.paperId,
        paperTitle: opts?.paperTitle,
        messages: [],
        updatedAt: Date.now(),
      };
      persist([conv, ...conversations]);
      setActiveId(id);
      return id;
    },
    [conversations, persist],
  );

  const saveActive = useCallback(
    (messages: ChatMessage[], opts?: { paperId?: number; paperTitle?: string }) => {
      const now = Date.now();
      const id = activeId ?? _newId();
      const existing = conversations.find((c) => c.id === id);
      const conv: Conversation = {
        id,
        title: existing?.title && existing.title !== "New chat" ? existing.title : _deriveTitle(messages),
        paperId: opts?.paperId ?? existing?.paperId,
        paperTitle: opts?.paperTitle ?? existing?.paperTitle,
        messages,
        updatedAt: now,
      };
      const next = existing
        ? conversations.map((c) => (c.id === id ? conv : c))
        : [conv, ...conversations];
      persist(next);
      if (!activeId) setActiveId(id);
    },
    [activeId, conversations, persist],
  );

  const deleteConversation = useCallback(
    (id: string) => {
      const next = conversations.filter((c) => c.id !== id);
      persist(next);
      if (activeId === id) setActiveId(null);
    },
    [activeId, conversations, persist],
  );

  const clearAll = useCallback(() => {
    persist([]);
    setActiveId(null);
  }, [persist]);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  return {
    conversations,
    activeId,
    active,
    selectConversation,
    startNew,
    saveActive,
    deleteConversation,
    clearAll,
    hydrated,
  };
}
