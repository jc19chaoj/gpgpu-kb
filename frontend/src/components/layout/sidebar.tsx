"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BookOpen, MessageCircle, Newspaper, BarChart3, Cpu, X } from "lucide-react";

const navItems = [
  { href: "/", label: "Browse", icon: BookOpen },
  { href: "/chat", label: "Chat (RAG)", icon: MessageCircle },
  { href: "/reports", label: "Daily Reports", icon: Newspaper },
  { href: "/stats", label: "Stats", icon: BarChart3 },
];

interface SidebarProps {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile backdrop */}
      <div
        aria-hidden
        onClick={onMobileClose}
        className={cn(
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-200 md:hidden",
          mobileOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
      />

      <aside
        className={cn(
          // Mobile: fixed off-canvas drawer
          "fixed inset-y-0 left-0 z-50 w-64 max-w-[80vw] border-r border-zinc-800 bg-zinc-950 text-zinc-100 flex flex-col h-dvh transform transition-transform duration-200 ease-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // Desktop: persistent rail
          "md:static md:translate-x-0 md:w-60 md:max-w-none md:shrink-0 md:z-auto"
        )}
        aria-label="Primary navigation"
      >
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-emerald-400" />
            <span className="font-semibold text-sm">GPGPU KB</span>
          </div>
          <button
            type="button"
            onClick={onMobileClose}
            className="md:hidden -mr-1 p-1.5 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors"
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 md:py-2 rounded-md text-sm transition-colors",
                pathname === item.href
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
    </>
  );
}
