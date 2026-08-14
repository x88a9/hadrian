import { cn } from "@/lib/utils";
import { fmtPct, fmtR } from "@/lib/format";
import { fmtPctValue, fmtUsd } from "@/lib/live-format";
import type { LiveMetrics } from "@/lib/types";

function MetricCard({
  label,
  value,
  hint,
  accent,
  highlight,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-xl border p-4",
        highlight
          ? "border-emerald-500/40 bg-emerald-500/[0.04] ring-1 ring-emerald-500/20"
          : "border-zinc-800 bg-zinc-900/30",
      )}
    >
      <span
        className={cn(
          "text-[11px] uppercase tracking-wider",
          highlight ? "text-emerald-300/80" : "text-zinc-500",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-xl tabular-nums text-zinc-100",
          accent,
        )}
      >
        {value}
      </span>
      {hint ? (
        <span className="text-[11px] text-zinc-600">{hint}</span>
      ) : null}
    </div>
  );
}

// Vorzeichen-abhaengige Farbe fuer PnL / R (positiv gruen, negativ rot).
function signAccent(value: number | null | undefined): string | undefined {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return undefined;
  }
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return undefined;
}

interface LiveMetricsCardsProps {
  metrics: LiveMetrics;
}

export function LiveMetricsCards({ metrics }: LiveMetricsCardsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <MetricCard
        label="Netto-PnL"
        value={fmtUsd(metrics.total_pnl_usd, { sign: true })}
        accent={signAccent(metrics.total_pnl_usd)}
        hint="realisiert, netto"
      />
      <MetricCard
        label="Total R"
        value={fmtR(metrics.total_r)}
        accent={signAccent(metrics.total_r)}
      />
      <MetricCard
        label="Win-Rate"
        value={fmtPct(metrics.win_rate)}
        hint={`${metrics.wins}W · ${metrics.losses}L`}
      />
      <MetricCard
        label="Ø Deviation"
        value={fmtPctValue(metrics.avg_deviation_pct)}
        hint="Ausführungsqualität"
        highlight
      />
      <MetricCard
        label="Kontostand"
        value={fmtUsd(metrics.current_balance)}
      />
      <MetricCard
        label="Offen / Geschlossen"
        value={`${metrics.open_count} / ${metrics.closed_count}`}
      />
    </div>
  );
}
