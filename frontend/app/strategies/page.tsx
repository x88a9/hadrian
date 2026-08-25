"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Plus, RotateCw, ServerCrash } from "lucide-react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { StrategiesTable } from "@/components/strategies-table";
import { StrategyDuplicateDialog } from "@/components/strategy-duplicate-dialog";
import { StrategyFormDialog } from "@/components/strategy-form-dialog";
import { Button } from "@/components/ui/button";
import { ApiError, deleteStrategy, getStrategies } from "@/lib/api";
import type { StrategySummary } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; strategies: StrategySummary[] }
  | { status: "error"; message: string; offline: boolean };

export default function StrategiesPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [createOpen, setCreateOpen] = useState(false);
  const [duplicating, setDuplicating] = useState<StrategySummary | null>(null);
  const [deleting, setDeleting] = useState<StrategySummary | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setState({ status: "loading" });
    try {
      const items = await getStrategies();
      setState({ status: "ready", strategies: items });
    } catch (err) {
      const offline = err instanceof ApiError && err.status === 0;
      const message =
        err instanceof ApiError
          ? offline
            ? "Backend nicht erreichbar. Läuft der API-Server?"
            : err.message
          : err instanceof Error
            ? err.message
            : "Unbekannter Fehler beim Laden.";
      setState({ status: "error", message, offline });
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
            Hadrian³
          </span>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
            Strategien
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {state.status === "ready"
              ? `${state.strategies.length} Strategien`
              : "Regel-Definitionen, Backtests und Versionen des Strategy-Designers."}
          </p>
        </div>
        <Button
          onClick={() => setCreateOpen(true)}
          className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
        >
          <Plus className="size-4" />
          Neue Strategie
        </Button>
      </header>

      <StrategyFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => void load(false)}
      />

      <StrategyDuplicateDialog
        open={duplicating !== null}
        onOpenChange={(next) => {
          if (!next) setDuplicating(null);
        }}
        strategy={duplicating}
        onDuplicated={() => {
          setDuplicating(null);
          void load(false);
        }}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(next) => {
          if (!next) setDeleting(null);
        }}
        title={`Strategie „${deleting?.name ?? ""}" löschen?`}
        description="Löscht die Strategie unwiderruflich, inklusive aller Versionen und Backtest-Ergebnisse."
        confirmLabel="Endgültig löschen"
        destructive
        onConfirm={async () => {
          if (!deleting) return;
          await deleteStrategy(deleting.id);
          setDeleting(null);
          await load(false);
        }}
      />

      {state.status === "loading" ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Strategien werden geladen…
        </div>
      ) : null}

      {state.status === "error" ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/30 px-6 py-20 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950 text-zinc-400">
            {state.offline ? (
              <ServerCrash className="size-6" />
            ) : (
              <AlertTriangle className="size-6" />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-200">
              Strategien konnten nicht geladen werden
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              {state.message}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void load(true)}
            className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
          >
            <RotateCw className="size-4" />
            Erneut versuchen
          </Button>
        </div>
      ) : null}

      {state.status === "ready" ? (
        state.strategies.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
            <p className="text-sm font-medium text-zinc-300">
              Noch keine Strategien
            </p>
            <p className="max-w-md text-sm text-zinc-500">
              Über „Neue Strategie" oben rechts eine deklarative oder
              Python-Strategie anlegen.
            </p>
          </div>
        ) : (
          <StrategiesTable
            strategies={state.strategies}
            onDuplicate={(s) => setDuplicating(s)}
            onDelete={(s) => setDeleting(s)}
          />
        )
      ) : null}
    </div>
  );
}
