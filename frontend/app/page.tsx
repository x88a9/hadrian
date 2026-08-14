import Link from "next/link";
import { ArrowUpRight, LineChart, Table2, LayoutDashboard } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const navItems = [
  {
    href: "/systems",
    title: "Systems",
    description:
      "Alle Trading-Systeme mit OOS-EV, ECE und Composite-Grade im Überblick.",
    icon: LineChart,
  },
  {
    href: "/trades",
    title: "Trade Explorer",
    description:
      "Einzelne Trades filtern, sortieren und in R-Einheiten analysieren.",
    icon: Table2,
  },
  {
    href: "/dashboard",
    title: "Portfolio Dashboard",
    description:
      "Aggregierte Kennzahlen und Equity-Kurven über das gesamte Portfolio.",
    icon: LayoutDashboard,
  },
] as const;

export default function Home() {
  return (
    <div className="flex flex-col justify-center py-8">
      <header className="mb-14">
        <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
          Hadrian³ · Phase 1
        </span>
        <h1 className="mt-4 text-6xl font-semibold tracking-tight text-zinc-50">
          Hadrian³
        </h1>
        <p className="mt-3 text-lg text-zinc-400">Trading Analytics Platform</p>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        {navItems.map(({ href, title, description, icon: Icon }) => (
          <Card
            key={href}
            className="group border-zinc-800 bg-zinc-900/40 transition-colors hover:border-zinc-700 hover:bg-zinc-900/70"
          >
            <CardHeader>
              <div className="mb-2 flex items-center justify-between">
                <span className="flex size-10 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950 text-zinc-300">
                  <Icon className="size-5" />
                </span>
                <ArrowUpRight className="size-4 text-zinc-600 transition-colors group-hover:text-zinc-300" />
              </div>
              <CardTitle className="text-zinc-100">{title}</CardTitle>
              <CardDescription className="text-zinc-500">
                {description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                render={<Link href={href} />}
                variant="secondary"
                className="w-full bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
              >
                Öffnen
              </Button>
            </CardContent>
          </Card>
        ))}
      </section>

      <footer className="mt-16 text-xs text-zinc-600">
        Zielrouten folgen in Phase 1. Systematisches Krypto-Futures-Trading,
        R-basiert und netto nach Kosten.
      </footer>
    </div>
  );
}
