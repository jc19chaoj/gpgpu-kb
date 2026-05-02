"use client";

import { Menu, Cpu } from "lucide-react";
import pkg from "../../../package.json";

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  return (
    <header className="h-12 border-b border-zinc-800 flex items-center px-3 sm:px-4 bg-zinc-950/70 backdrop-blur-sm sticky top-0 z-30">
      <button
        type="button"
        onClick={onMenuClick}
        className="md:hidden -ml-1 mr-2 p-2 rounded-md text-zinc-300 hover:text-white hover:bg-zinc-800/60 transition-colors"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>
      <div className="flex items-center gap-2 md:hidden">
        <Cpu className="h-4 w-4 text-emerald-400" />
        <span className="text-sm font-semibold">GPGPU KB</span>
      </div>
      <div className="flex-1" />
      <span className="text-[10px] sm:text-xs text-zinc-500">
        v{pkg.version}
      </span>
    </header>
  );
}
