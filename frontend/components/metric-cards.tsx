import { GradeBadge } from "@/components/grade-badge";
import { cn } from "@/lib/utils";
import { fmtDate, fmtInt, fmtNum, fmtPct, fmtR } from "@/lib/format";
import type { MetricsBlock, SystemMetrics } from "@/lib/types";

type Segment = "all" | "is" | "oos";

const SEGMENTS: Array<{ key: Segment; label: string; hint: string }> = [
  { key: "all", label: "All", hint: "Gesamt" },
  { key: "is", label: "In-Sample", hint: "IS · Kontext" },
  { key: "oos", label: "Out-of-Sample", hint: "OOS · wichtigste Kennzahl" },
];

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-zinc-500">{label}</span>
      <span
        className={cn(
          "font-mono text-sm tabular-nums text-zinc-200",
          accent,
        )}
      >
        {value}
      </span>
    </div>
  );
}

function rAccent(value: number | null): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return undefined;
}

function MetricsColumn({
  block,
  segment,
}: {
  block: MetricsBlock;
  segment: (typeof SEGMENTS)[number];
}) {
  const highlight = segment.key === "oos";
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border p-4",
        highlight
          ? "border-emerald-500/40 bg-emerald-500/[0.04] ring-1 ring-emerald-500/20"
          : "border-zinc-800 bg-zinc-900/30",
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <div
            className={cn(
              "text-sm font-medium",
              highlight ? "text-emerald-300" : "text-zinc-200",
            )}
          >
            {segment.label}
          </div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-600">
            {segment.hint}
          </div>
        </div>
        <GradeBadge grade={block.composite_grade} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Stat label="EV" value={fmtR(block.ev)} accent={rAccent(block.ev)} />
        <Stat label="Win Rate" value={fmtPct(block.win_rate)} />
        <Stat
          label="Total R"
          value={fmtR(block.total_r)}
          accent={rAccent(block.total_r)}
        />
        <Stat label="ECE" value={fmtNum(block.ece, 3)} />
        <Stat label="EVol" value={fmtNum(block.evol, 3)} />
        <Stat label="Composite" value={fmtNum(block.composite_score, 3)} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t border-zinc-800 pt-3">
        <GradeLabel label="EV" grade={block.ev_grade} />
        <GradeLabel label="ECE" grade={block.ece_grade} />
        <GradeLabel label="EVol" grade={block.evol_grade} />
      </div>

      <div className="flex flex-col gap-1.5 border-t border-zinc-800 pt-3">
        <div className="text-[11px] uppercase tracking-wider text-zinc-600">
          Risiko &amp; Verteilung
        </div>
        <Stat
          label="Profit Factor"
          value={fmtNum(block.profit_factor ?? null, 2)}
        />
        <Stat
          label="Max DD (R)"
          value={fmtNum(block.max_drawdown_r ?? null, 2)}
          accent="text-red-400"
        />
        <Stat label="RoMaD" value={fmtNum(block.romad ?? null, 2)} />
        <Stat label="Skew" value={fmtNum(block.skewness ?? null, 2)} />
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-xs text-zinc-500">Perzentile</span>
          <span className="font-mono text-[11px] tabular-nums text-zinc-300">
            {[
              block.r_p05 ?? null,
              block.r_p25 ?? null,
              block.r_p50 ?? null,
              block.r_p75 ?? null,
              block.r_p95 ?? null,
            ]
              .map((v) => fmtNum(v, 2))
              .join(" · ")}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 border-t border-zinc-800 pt-3">
        <Stat label="Trades" value={fmtInt(block.total_trades)} />
        <Stat label="Wins" value={fmtInt(block.wins)} />
        <Stat label="Losses" value={fmtInt(block.losses)} />
        <Stat label="Avg Win" value={fmtR(block.avg_win_r)} />
        <Stat label="Avg Loss" value={fmtR(block.avg_loss_r)} />
      </div>

      <div className="border-t border-zinc-800 pt-3 text-[11px] text-zinc-500">
        <div className="flex items-center justify-between">
          <span>Zeitraum</span>
          <span className="font-mono text-zinc-400">
            {fmtDate(block.first_trade_at)} – {fmtDate(block.last_trade_at)}
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span>Span</span>
          <span className="font-mono text-zinc-400">
            {block.span_days === null
              ? "—"
              : `${fmtNum(block.span_days, 1)} Tage`}
          </span>
        </div>
      </div>
    </div>
  );
}

function GradeLabel({
  label,
  grade,
}: {
  label: string;
  grade: MetricsBlock["ev_grade"];
}) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500">
      {label}
      <GradeBadge grade={grade} className="h-4 min-w-6 px-1 text-[10px]" />
    </span>
  );
}

interface MetricCardsProps {
  metrics: SystemMetrics;
}

export function MetricCards({ metrics }: MetricCardsProps) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {SEGMENTS.map((seg) => (
        <MetricsColumn key={seg.key} block={metrics[seg.key]} segment={seg} />
      ))}
    </div>
  );
}
