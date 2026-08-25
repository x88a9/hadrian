"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/systems", label: "Systems" },
  { href: "/strategies", label: "Strategies" },
  { href: "/live", label: "Live" },
  { href: "/risk", label: "Risk" },
  { href: "/trades", label: "Trades" },
  { href: "/concepts", label: "Concepts" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/settings", label: "Settings" },
] as const;

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
      <nav className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-6">
        <Link
          href="/"
          className="text-sm font-semibold tracking-tight text-zinc-100 transition-colors hover:text-white"
        >
          Hadrian³
        </Link>
        <div className="flex items-center gap-1">
          {links.map(({ href, label }) => {
            const active =
              pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                )}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
