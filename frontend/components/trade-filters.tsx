"use client";

import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Direction, SystemSummary, TradeSource, WinLoss } from "@/lib/types";

// Serverseitig anwendbare Filter fuer den Trade-Explorer.
// undefined bzw. "" bedeutet jeweils "Alle".
export interface TradeFilterState {
  system_id?: number;
  direction?: Direction;
  win_loss?: WinLoss;
  source?: TradeSource;
  date_from?: string;
  date_to?: string;
}

export const EMPTY_FILTERS: TradeFilterState = {};

interface TradeFiltersProps {
  systems: SystemSummary[];
  value: TradeFilterState;
  onChange: (next: TradeFilterState) => void;
  disabled?: boolean;
}

const fieldLabel = "text-[0.7rem] font-medium uppercase tracking-wide text-zinc-500";

const selectClass = cn(
  "h-8 min-w-32 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 text-sm text-zinc-100",
  "outline-none transition-colors hover:border-zinc-700",
  "focus-visible:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-700",
  "disabled:pointer-events-none disabled:opacity-50",
);

const dateClass = cn(
  "h-8 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 text-sm text-zinc-100",
  "outline-none transition-colors hover:border-zinc-700",
  "focus-visible:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-700",
  "disabled:pointer-events-none disabled:opacity-50 [color-scheme:dark]",
);

export function TradeFilters({
  systems,
  value,
  onChange,
  disabled,
}: TradeFiltersProps) {
  // Jede Aenderung ersetzt den kompletten Filterstate -> Parent setzt offset zurueck.
  function patch(part: Partial<TradeFilterState>) {
    onChange({ ...value, ...part });
  }

  const hasActive =
    value.system_id !== undefined ||
    value.direction !== undefined ||
    value.win_loss !== undefined ||
    value.source !== undefined ||
    Boolean(value.date_from) ||
    Boolean(value.date_to);

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>System</span>
        <select
          className={selectClass}
          disabled={disabled}
          value={value.system_id ?? ""}
          onChange={(e) =>
            patch({
              system_id: e.target.value ? Number(e.target.value) : undefined,
            })
          }
        >
          <option value="">Alle</option>
          {systems.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>Direction</span>
        <select
          className={selectClass}
          disabled={disabled}
          value={value.direction ?? ""}
          onChange={(e) =>
            patch({
              direction: (e.target.value || undefined) as
                | Direction
                | undefined,
            })
          }
        >
          <option value="">Alle</option>
          <option value="long">Long</option>
          <option value="short">Short</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>W/L</span>
        <select
          className={selectClass}
          disabled={disabled}
          value={value.win_loss ?? ""}
          onChange={(e) =>
            patch({
              win_loss: (e.target.value || undefined) as WinLoss | undefined,
            })
          }
        >
          <option value="">Alle</option>
          <option value="win">Win</option>
          <option value="loss">Loss</option>
          <option value="draw">Draw</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>Source</span>
        <select
          className={selectClass}
          disabled={disabled}
          value={value.source ?? ""}
          onChange={(e) =>
            patch({
              source: (e.target.value || undefined) as
                | TradeSource
                | undefined,
            })
          }
        >
          <option value="">Alle</option>
          <option value="manual">Manual</option>
          <option value="auto">Auto</option>
          <option value="ui">UI</option>
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>Von</span>
        <input
          type="date"
          className={dateClass}
          disabled={disabled}
          value={value.date_from ?? ""}
          onChange={(e) =>
            patch({ date_from: e.target.value || undefined })
          }
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>Bis</span>
        <input
          type="date"
          className={dateClass}
          disabled={disabled}
          value={value.date_to ?? ""}
          onChange={(e) => patch({ date_to: e.target.value || undefined })}
        />
      </label>

      <Button
        variant="outline"
        size="sm"
        disabled={disabled || !hasActive}
        onClick={() => onChange({ ...EMPTY_FILTERS })}
        className="border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
      >
        <RotateCcw />
        Reset
      </Button>
    </div>
  );
}
