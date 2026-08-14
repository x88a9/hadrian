"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Cpu,
  Loader2,
  Plus,
  RotateCw,
  ServerCrash,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ImportButton } from "@/components/import-button";
import { SystemFormDialog } from "@/components/system-form-dialog";
import { SystemsTable } from "@/components/systems-table";
import { ApiError, getSystems, importProgrammatic } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { SystemSummary } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; systems: SystemSummary[]; splitDate: string }
  | { status: "error"; message: string; offline: boolean };

export default function SystemsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [createOpen, setCreateOpen] = useState(false);

  const existingNames = useMemo(
    () => (state.status === "ready" ? state.systems.map((s) => s.name) : []),
    [state],
  );

  const load = useCallback(async (initial = false) => {
    if (initial) setState({ status: "loading" });
    try {
      const res = await getSystems();
      setState({
        status: "ready",
        systems: res.items,
        splitDate: res.split_date,
      });
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
            Systeme
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {state.status === "ready" ? (
              <>
                {state.systems.length} Systeme · OOS ab{" "}
                <span className="font-mono text-zinc-400">
                  {fmtDate(state.splitDate)}
                </span>
              </>
            ) : (
              "Alle Trading-Systeme mit OOS-EV, ECE und Composite-Grade."
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-start justify-end gap-3">
          <Button
            onClick={() => setCreateOpen(true)}
            className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
          >
            <Plus className="size-4" />
            Neues System
          </Button>
          <ImportButton
            onImported={() => void load(false)}
            importFn={importProgrammatic}
            label="Import programmatisch"
            loadingLabel="Importiere…"
            idleIcon={<Cpu className="size-4" />}
            buttonClassName="border border-violet-500/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20"
          />
          <ImportButton onImported={() => void load(false)} />
        </div>
      </header>

      <SystemFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        mode="create"
        existingNames={existingNames}
        onSaved={() => void load(false)}
      />

      {state.status === "loading" ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Systeme werden geladen…
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
              Systeme konnten nicht geladen werden
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
        state.systems.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
            <p className="text-sm font-medium text-zinc-300">
              Noch keine Systeme — Import starten
            </p>
            <p className="max-w-md text-sm text-zinc-500">
              Über „Import xlsx" oben rechts das Backtesting-Repository einlesen.
            </p>
          </div>
        ) : (
          <SystemsTable systems={state.systems} />
        )
      ) : null}
    </div>
  );
}
