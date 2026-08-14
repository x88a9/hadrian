"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { ApiError, updateSystem } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

// Lebenszyklus-Reihenfolge (D-Wissen: backtest -> live_testing -> active -> retired).
const LIFECYCLE: { value: SystemStatus; label: string; active: string }[] = [
  {
    value: "backtest",
    label: "Backtest",
    active: "bg-zinc-500/20 text-zinc-100 border-zinc-400/40",
  },
  {
    value: "live_testing",
    label: "Live Testing",
    active: "bg-amber-500/20 text-amber-200 border-amber-400/40",
  },
  {
    value: "active",
    label: "Active",
    active: "bg-emerald-500/20 text-emerald-200 border-emerald-400/40",
  },
  {
    value: "retired",
    label: "Retired",
    active: "bg-red-500/20 text-red-200 border-red-400/40",
  },
];

export interface StatusSwitcherProps {
  systemId: number;
  status: SystemStatus;
  onChanged: () => void;
}

// Lebenszyklus-Kontrolle im System-Detail-Header: klickbare Stufen.
export function StatusSwitcher({
  systemId,
  status,
  onChanged,
}: StatusSwitcherProps) {
  const [pending, setPending] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function switchTo(next: SystemStatus) {
    if (next === status || pending) return;
    setPending(next);
    setError(null);
    try {
      await updateSystem(systemId, { status: next });
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : "Statuswechsel fehlgeschlagen.",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="inline-flex overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/40">
        {LIFECYCLE.map((step, i) => {
          const isCurrent = step.value === status;
          const isPending = pending === step.value;
          return (
            <button
              key={step.value}
              type="button"
              onClick={() => void switchTo(step.value)}
              disabled={pending !== null || isCurrent}
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                i > 0 && "border-l border-zinc-800",
                isCurrent
                  ? cn("border-y-0", step.active)
                  : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-200",
                pending !== null && !isPending && "opacity-60",
                "disabled:cursor-default",
              )}
            >
              {isPending ? <Loader2 className="size-3 animate-spin" /> : null}
              {step.label}
            </button>
          );
        })}
      </div>
      {error ? <p className="text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
