"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  Download,
  Loader2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError, importXlsx } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import type { ImportRunResponse, ImportTabResult } from "@/lib/types";

interface ImportButtonProps {
  onImported?: () => void;
  // Optionale Parametrisierung: Standard = xlsx-Import (unveraendertes Verhalten).
  importFn?: () => Promise<ImportRunResponse>;
  label?: string;
  loadingLabel?: string;
  idleIcon?: ReactNode;
  buttonClassName?: string;
}

interface StatItemProps {
  label: string;
  value: number;
  tone?: "default" | "warn" | "good";
}

function StatItem({ label, value, tone = "default" }: StatItemProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-zinc-500">{label}</span>
      <span
        className={cn(
          "font-mono text-lg font-semibold tabular-nums",
          tone === "warn" && "text-amber-400",
          tone === "good" && "text-emerald-400",
          tone === "default" && "text-zinc-100",
        )}
      >
        {fmtInt(value)}
      </span>
    </div>
  );
}

export function ImportButton({
  onImported,
  importFn = importXlsx,
  label = "Import xlsx",
  loadingLabel = "Importiere…",
  idleIcon = <Download className="size-4" />,
  buttonClassName = "bg-zinc-100 text-zinc-900 hover:bg-white",
}: ImportButtonProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTabs, setShowTabs] = useState(false);

  async function handleImport() {
    setLoading(true);
    setError(null);
    try {
      const run = await importFn();
      setResult(run);
      setShowTabs(false);
      onImported?.();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 0
            ? `Backend nicht erreichbar (${err.message}).`
            : err.message
          : err instanceof Error
            ? err.message
            : "Unbekannter Fehler beim Import.";
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // Nur unfertige/uebersprungene Tabs sind erklaerungsbeduerftig.
  const flagged: ImportTabResult[] = result
    ? result.tab_results.filter((t) => t.status !== "complete")
    : [];

  return (
    <div className="flex flex-col items-end gap-3">
      <Button
        onClick={handleImport}
        disabled={loading}
        className={buttonClassName}
      >
        {loading ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            {loadingLabel}
          </>
        ) : (
          <>
            {idleIcon}
            {label}
          </>
        )}
      </Button>

      {error ? (
        <div className="flex w-full items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="flex-1">
            <p className="font-medium text-red-200">Import fehlgeschlagen</p>
            <p className="mt-0.5 text-red-300/90">{error}</p>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-red-400/70 transition-colors hover:text-red-200"
            aria-label="Schließen"
          >
            <X className="size-4" />
          </button>
        </div>
      ) : null}

      {result ? (
        <div className="w-full rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-left">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-100">
                Import abgeschlossen
              </p>
              <p className="mt-0.5 font-mono text-xs text-zinc-500">
                {result.file_path}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setResult(null)}
              className="text-zinc-500 transition-colors hover:text-zinc-200"
              aria-label="Schließen"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
            <StatItem label="Tabs gesamt" value={result.tabs_total} />
            <StatItem
              label="Systeme komplett"
              value={result.systems_complete}
              tone="good"
            />
            <StatItem
              label="Unvollständig"
              value={result.systems_incomplete}
              tone={result.systems_incomplete > 0 ? "warn" : "default"}
            />
            <StatItem
              label="Übersprungen"
              value={result.tabs_skipped}
              tone={result.tabs_skipped > 0 ? "warn" : "default"}
            />
            <StatItem
              label="Trades importiert"
              value={result.trades_imported}
            />
          </div>

          {flagged.length > 0 ? (
            <div className="mt-4 border-t border-zinc-800 pt-3">
              <button
                type="button"
                onClick={() => setShowTabs((v) => !v)}
                className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 transition-colors hover:text-zinc-200"
              >
                <ChevronDown
                  className={cn(
                    "size-3.5 transition-transform",
                    showTabs && "rotate-180",
                  )}
                />
                {flagged.length} Tab(s) mit Hinweis
              </button>
              {showTabs ? (
                <ul className="mt-2 flex flex-col gap-1">
                  {flagged.map((t) => (
                    <li
                      key={t.tab}
                      className="flex items-start gap-2 rounded-md bg-zinc-950/60 px-3 py-2 text-xs"
                    >
                      <span
                        className={cn(
                          "mt-px shrink-0 font-medium",
                          t.status === "skipped"
                            ? "text-red-400"
                            : "text-amber-400",
                        )}
                      >
                        {t.status === "skipped"
                          ? "übersprungen"
                          : "unvollständig"}
                      </span>
                      <span className="font-mono text-zinc-300">{t.tab}</span>
                      {t.message ? (
                        <span className="text-zinc-500">— {t.message}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
