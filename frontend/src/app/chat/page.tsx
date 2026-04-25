"use client";

import { useState, useRef, useEffect } from "react";
import { chat } from "@/lib/api";
import { Paper } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Cpu, User, FileText, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Paper[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "I'm your GPGPU research assistant. Ask me anything about papers, architectures, optimizations, or trends in the knowledge base. I'll search the most relevant papers and answer based on the latest research.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const query = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoading(true);

    try {
      const res = await chat({ query, top_k: 5 });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't process that query. Is the backend running?" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      <ScrollArea className="flex-1 px-6">
        <div className="space-y-4 py-4">
          {messages.map((msg, i) => (
            <div key={i} className="flex gap-3">
              <div className="shrink-0 mt-1">
                {msg.role === "assistant" ? (
                  <Cpu className="h-5 w-5 text-emerald-400" />
                ) : (
                  <User className="h-5 w-5 text-blue-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-zinc-400 mb-1">
                  {msg.role === "assistant" ? "Assistant" : "You"}
                </div>
                <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-zinc-800">
                    <p className="text-xs text-zinc-500 mb-2">Sources:</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((s) => (
                        <Link key={s.id} href={`/paper/${s.id}`}>
                          <Badge variant="outline" className="cursor-pointer hover:bg-zinc-800 text-xs border-zinc-700 text-zinc-400">
                            <FileText className="h-3 w-3 mr-1" />
                            {s.title.slice(0, 60)}{s.title.length > 60 ? "..." : ""}
                          </Badge>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <Loader2 className="h-5 w-5 text-emerald-400 animate-spin shrink-0 mt-1" />
              <div className="text-sm text-zinc-500">Searching knowledge base...</div>
            </div>
          )}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      <div className="border-t border-zinc-800 p-4">
        <div className="flex items-center gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about GPU architectures, attention mechanisms, LLM training..."
            className="flex-1 bg-zinc-900 border-zinc-800 text-sm"
            disabled={loading}
          />
          <Button type="submit" size="icon" disabled={loading || !input.trim()}
                  className="bg-emerald-600 hover:bg-emerald-700" onClick={handleSend}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-[10px] text-zinc-600 mt-2">
          Answers are based on papers in the knowledge base. Results may vary by processing state.
        </p>
      </div>
    </div>
  );
}
