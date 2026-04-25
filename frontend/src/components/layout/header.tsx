import pkg from "../../../package.json";

export function Header() {
  return (
    <header className="h-12 border-b border-zinc-800 flex items-center px-4 bg-zinc-950/50">
      <div className="flex-1" />
      <span className="text-xs text-zinc-500">GPGPU Knowledge Base v{pkg.version}</span>
    </header>
  );
}
