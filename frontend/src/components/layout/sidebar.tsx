"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BookOpen, MessageCircle, Newspaper, BarChart3, Cpu } from "lucide-react";

const navItems = [
  { href: "/", label: "Browse", icon: BookOpen },
  { href: "/chat", label: "Chat (RAG)", icon: MessageCircle },
  { href: "/reports", label: "Daily Reports", icon: Newspaper },
  { href: "/stats", label: "Stats", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 border-r border-zinc-800 bg-zinc-950 text-zinc-100 flex flex-col h-screen shrink-0">
      <div className="p-4 border-b border-zinc-800 flex items-center gap-2">
        <Cpu className="h-5 w-5 text-emerald-400" />
        <span className="font-semibold text-sm">GPGPU KB</span>
      </div>
      <nav className="flex-1 p-2">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === item.href
                ? "bg-zinc-800 text-white"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
