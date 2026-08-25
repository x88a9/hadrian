"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  History,
  Loader2,
  Play,
  RotateCcw,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EngineTradesTable } from "@/components/engine-trades-table";
import { EquityCurve } from "@/components/equity-curve";
import { MetricCards } from "@/components/metric-cards";
import { RHistogram } from "@/components/r-histogram";
import { StrategyBlocks, type DefinitionEditorShared } from "@/components/strategy-blocks";
import { StrategyEditor } from "@/components/strategy-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  backtestStrategy,
  deleteStrategy,
  getBacktest,
  getStrategy,
  getStrategyBacktests,
  updateStrategy,
  validateStrategy,
} from "@/lib/api";
import { fmtDateTime, fmtInt, fmtR } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  BacktestRun,
  BacktestRunSummary,
  EngineTrade,
  StrategyDefinition,
  StrategyDetail,
  StrategyVersion,
  SystemMetrics,
  Trade,
} from "@/lib/types";

type TabKey = "editor" | "blocks" | "backtest" | "versions" | "trades";

const TAB_LABEL: Record<TabKey, string> = {
  editor: "Editor",
  blocks: "Blöcke",
  backtest: "Backtest",
  versions: "Versionen",
  trades: "Trades",
};

const RULES_LABEL: Record<StrategyDefinition["rules"], string> = {
  declarative: "deklarativ",
  python: "python",
};

const RULES_COLOR: Record<StrategyDefinition["rules"], string> = {
  declarative: "bg-cyan-500/10 text-cyan-300 border-cyan-500/30",
  python: "bg-violet-500/10 text-violet-300 border-violet-500/30",
};

// EquityCurve/RHistogram sind auf die System-Trade-Form gebaut. Ein
// EngineTrade traegt dieselbe Kerninformation (Datum, R) unter anderen
// Feldnamen -> minimaler Adapter statt Neubau der Charts.
function engineTradesToTrades(trades: EngineTrade[]): Trade[] {
  return trades.map((t, i) => ({
    id: i + 1,
    system_id: 0,
    system_name: "",
    trade_datetime: t.entry_ts,
    zone: t.tag,
    timeframe: null,
    entry: t.entry_price,
    sl: t.stop_price,
    exit: t.exit_price,
    direction: t.direction,
    r_value: t.r_value,
    win_loss:
      t.win_loss === "win" || t.win_loss === "loss" || t.win_loss === "draw"
        ? t.win_loss
        : null,
    source: "auto",
  }));
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

// Trennt die Metadaten (alles ausser python_source) aus einer Definition, als
// huebsch gedrucktes JSON — die Grundlage fuer den Meta-Editor im Python-Modus
// und den einzigen Editor im deklarativen Modus.
function metaText(definition: StrategyDefinition): string {
  const meta: Partial<StrategyDefinition> = { ...definition };
  delete meta.python_source;
  return JSON.stringify(meta, null, 2);
}

export default function StrategyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const strategyId = Number(id);
  const router = useRouter();

  const [strategy, setStrategy] = useState<StrategyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ status: number; message: string } | null>(
    null,
  );
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>("editor");

  const reload = useCallback(async () => {
    try {
      const detail = await getStrategy(strategyId);
      setStrategy(detail);
      setError(null);
      return detail;
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ status: err.status, message: err.message });
      } else {
        setError({
          status: 0,
          message: err instanceof Error ? err.message : "Unbekannter Fehler",
        });
      }
      return null;
    }
  }, [strategyId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    reload().finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [reload]);

  return (
    <div className="flex flex-col gap-8 py-4">
      <Link
        href="/strategies"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-300"
      >
        <ArrowLeft className="size-4" />
        Zurück zur Übersicht
      </Link>

      {loading && (
        <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
          Lade Strategie #{id} …
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6">
          <div className="mb-1 flex size-10 items-center justify-center rounded-md border border-red-900/50 bg-red-950/40 text-red-400">
            <AlertTriangle className="size-5" />
          </div>
          <p className="mt-2 text-lg font-semibold text-red-200">
            {error.status === 404
              ? `Strategie #${id} nicht gefunden`
              : "Strategie konnte nicht geladen werden"}
          </p>
          <p className="mt-1 text-sm text-red-300/80">
            {error.status === 0
              ? "Backend nicht erreichbar. Läuft das API (docker compose up)?"
              : error.message}
          </p>
        </div>
      )}

      {!loading && !error && strategy && (
        <StrategyDesignerBody
          strategy={strategy}
          setStrategy={setStrategy}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          onDeleteRequested={() => setDeleteOpen(true)}
        />
      )}

      {strategy ? (
        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          title={`Strategie „${strategy.name}" löschen?`}
          description="Löscht die Strategie unwiderruflich, inklusive aller Versionen und Backtest-Ergebnisse."
          confirmLabel="Endgültig löschen"
          destructive
          onConfirm={async () => {
            await deleteStrategy(strategy.id);
            router.push("/strategies");
          }}
        />
      ) : null}
    </div>
  );
}

function StrategyDesignerBody({
  strategy,
  setStrategy,
  activeTab,
  setActiveTab,
  onDeleteRequested,
}: {
  strategy: StrategyDetail;
  setStrategy: (s: StrategyDetail) => void;
  activeTab: TabKey;
  setActiveTab: (t: TabKey) => void;
  onDeleteRequested: () => void;
}) {
  const [activeRun, setActiveRun] = useState<BacktestRun | null>(null);

  // The definition being edited — shared by the Editor (JSON) and Blöcke
  // (blocks) tabs, so both are windows onto the exact same object: a change
  // made in one is immediately visible when switching to the other, and
  // Save from either goes through the same PUT /strategies/{id} call below.
  const [definition, setDefinition] = useState<StrategyDefinition>(strategy.definition);
  const [note, setNote] = useState("");
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<{ ok: boolean; errors: string[] } | null>(
    null,
  );
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Re-seed the shared definition when the strategy identity or its saved
  // version changes from outside this component (initial load, restore from
  // Versions tab).
  useEffect(() => {
    setDefinition(strategy.definition);
    setValidation(null);
    setSaveError(null);
    setSaved(false);
    setNote("");
  }, [strategy.id, strategy.current_version]);

  const handleValidate = useCallback(async () => {
    setValidating(true);
    setSaveError(null);
    setSaved(false);
    try {
      const res = await validateStrategy(definition);
      setValidation({ ok: res.ok, errors: res.errors });
    } catch (err) {
      setValidation(null);
      setSaveError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Validierung fehlgeschlagen.",
      );
    } finally {
      setValidating(false);
    }
  }, [definition]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const res = await validateStrategy(definition);
      setValidation({ ok: res.ok, errors: res.errors });
      if (!res.ok) return;
      const updated = await updateStrategy(strategy.id, {
        definition,
        note: note.trim() || undefined,
      });
      setStrategy(updated);
      setNote("");
      setSaved(true);
    } catch (err) {
      setSaveError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Speichern fehlgeschlagen.",
      );
    } finally {
      setSaving(false);
    }
  }, [definition, strategy.id, note, setStrategy]);

  const shared: DefinitionEditorShared = {
    note,
    setNote,
    validation,
    saveError,
    saved,
    saving,
    validating,
    onValidate: () => void handleValidate(),
    onSave: () => void handleSave(),
  };

  return (
    <>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-50">
            {strategy.name}
          </h1>
          <Badge
            variant="outline"
            className={cn("font-normal", RULES_COLOR[strategy.definition.rules])}
          >
            {RULES_LABEL[strategy.definition.rules]}
          </Badge>
          <Badge variant="outline" className="font-mono font-normal">
            v{strategy.current_version}
          </Badge>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="outline"
              onClick={onDeleteRequested}
              className="border-red-500/30 bg-transparent text-red-400/90 hover:bg-red-500/10 hover:text-red-300"
            >
              <Trash2 className="size-4" />
              Löschen
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span className="inline-flex items-center rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 font-mono text-zinc-300">
            {strategy.asset}
          </span>
          <span className="text-zinc-700">·</span>
          <span>{strategy.timeframe}</span>
          <span className="text-zinc-700">·</span>
          <span>{strategy.definition.direction}</span>
          <span className="text-zinc-700">·</span>
          <span>Aktualisiert {fmtDateTime(strategy.updated_at)}</span>
        </div>

        {strategy.description ? (
          <p className="max-w-prose text-sm leading-relaxed text-zinc-400">
            {strategy.description}
          </p>
        ) : null}
      </header>

      {/* Tab-Strip */}
      <div>
        <div className="mb-4 inline-flex overflow-hidden rounded-lg border border-zinc-800">
          {(Object.keys(TAB_LABEL) as TabKey[]).map((t, i) => (
            <button
              key={t}
              type="button"
              onClick={() => setActiveTab(t)}
              className={cn(
                "h-9 px-4 text-sm font-medium transition-colors",
                i > 0 && "border-l border-zinc-800",
                activeTab === t
                  ? "bg-zinc-800 text-zinc-100"
                  : "bg-zinc-900/40 text-zinc-400 hover:text-zinc-200",
              )}
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>

        {activeTab === "editor" && (
          <EditorPane
            key={`${strategy.id}:${strategy.current_version}`}
            strategy={strategy}
            definition={definition}
            setDefinition={setDefinition}
            shared={shared}
          />
        )}
        {activeTab === "blocks" && (
          <StrategyBlocks definition={definition} onChange={setDefinition} shared={shared} />
        )}
        {activeTab === "backtest" && (
          <BacktestPane
            strategy={strategy}
            activeRun={activeRun}
            setActiveRun={setActiveRun}
            setStrategy={setStrategy}
          />
        )}
        {activeTab === "versions" && (
          <VersionsPane strategy={strategy} setStrategy={setStrategy} />
        )}
        {activeTab === "trades" && <TradesPane activeRun={activeRun} />}
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// Editor
// --------------------------------------------------------------------------

function EditorPane({
  strategy,
  definition,
  setDefinition,
  shared,
}: {
  strategy: StrategyDetail;
  definition: StrategyDefinition;
  setDefinition: (d: StrategyDefinition) => void;
  shared: DefinitionEditorShared;
}) {
  const rules = strategy.definition.rules;
  // Local text state, seeded once from the shared definition at mount. The
  // parent remounts this pane (via `key`) whenever the strategy identity or
  // its saved version changes, so this never goes stale.
  const [meta, setMeta] = useState(() => metaText(definition));
  const [pythonSource, setPythonSource] = useState(() => definition.python_source ?? "");
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Push a parsed edit up into the shared definition immediately — this is
  // what makes "edit in JSON, switch to Blöcke" show the change without a
  // separate sync step. While the text is not valid JSON, the shared
  // definition simply keeps its last valid value and Save/Validate are
  // disabled below, rather than operating on stale or unparsable data.
  function push(nextMeta: string, nextPythonSource: string) {
    try {
      const parsed = JSON.parse(nextMeta) as Omit<StrategyDefinition, "python_source">;
      setDefinition({
        ...parsed,
        python_source: rules === "python" ? nextPythonSource : null,
      });
      setJsonError(null);
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : "Ungültiges JSON.");
    }
  }

  function handleMetaChange(next: string) {
    setMeta(next);
    push(next, pythonSource);
  }

  function handlePythonChange(next: string) {
    setPythonSource(next);
    push(meta, next);
  }

  const { note, setNote, validation, saveError, saved, validating, saving, onValidate, onSave } =
    shared;
  const blocked = jsonError !== null;

  return (
    <div className="flex flex-col gap-4">
      {rules === "python" ? (
        <>
          <div>
            <SectionTitle>Python-Quelltext</SectionTitle>
            <StrategyEditor
              value={pythonSource}
              onChange={handlePythonChange}
              language="python"
              height={420}
            />
          </div>
          <div>
            <SectionTitle>
              Metadaten (JSON) — Indikatoren, Risk, Costs, Parameter
            </SectionTitle>
            <StrategyEditor
              value={meta}
              onChange={handleMetaChange}
              language="json"
              height={280}
            />
          </div>
        </>
      ) : (
        <div>
          <SectionTitle>Definition (JSON)</SectionTitle>
          <StrategyEditor
            value={meta}
            onChange={handleMetaChange}
            language="json"
            height={560}
          />
        </div>
      )}

      {jsonError ? (
        <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          Ungültiges JSON — Änderungen werden erst übernommen, sobald der Text
          wieder gültiges JSON ist: {jsonError}
        </p>
      ) : null}

      {validation ? (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-sm",
            validation.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/30 bg-red-500/10 text-red-300",
          )}
        >
          <div className="flex items-center gap-2 font-medium">
            {validation.ok ? (
              <CheckCircle2 className="size-4 shrink-0" />
            ) : (
              <XCircle className="size-4 shrink-0" />
            )}
            {validation.ok ? "Definition gültig" : "Definition ungültig"}
          </div>
          {validation.errors.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1 pl-6 text-xs [list-style:disc]">
              {validation.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {saveError ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {saveError}
        </p>
      ) : null}

      {saved ? (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          Gespeichert als Version {strategy.current_version}.
        </p>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 border-t border-zinc-800 pt-4">
        <div className="flex min-w-64 flex-1 flex-col gap-1.5">
          <Label htmlFor="save-note">Notiz (optional)</Label>
          <Input
            id="save-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="z. B. Stop auf ATR umgestellt"
            autoComplete="off"
          />
        </div>
        <Button
          variant="outline"
          onClick={onValidate}
          disabled={validating || saving || blocked}
          className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
        >
          {validating ? <Loader2 className="size-4 animate-spin" /> : null}
          Validieren
        </Button>
        <Button onClick={onSave} disabled={saving || validating || blocked}>
          {saving ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Save className="size-4" />
          )}
          Speichern (neue Version)
        </Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Backtest
// --------------------------------------------------------------------------

function BacktestPane({
  strategy,
  activeRun,
  setActiveRun,
  setStrategy,
}: {
  strategy: StrategyDetail;
  activeRun: BacktestRun | null;
  setActiveRun: (r: BacktestRun | null) => void;
  setStrategy: (s: StrategyDetail) => void;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [persist, setPersist] = useState(true);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [pastRuns, setPastRuns] = useState<BacktestRunSummary[]>([]);
  const [pastRunsLoading, setPastRunsLoading] = useState(true);
  const [pastRunsError, setPastRunsError] = useState<string | null>(null);
  const [loadingRunId, setLoadingRunId] = useState<number | null>(null);

  const paramEntries = useMemo(
    () => Object.entries(strategy.definition.parameters),
    [strategy.definition.parameters],
  );

  const loadPastRuns = useCallback(async () => {
    setPastRunsLoading(true);
    setPastRunsError(null);
    try {
      const runs = await getStrategyBacktests(strategy.id);
      setPastRuns(runs);
    } catch (err) {
      setPastRunsError(
        err instanceof ApiError && err.status === 0
          ? "Backend nicht erreichbar."
          : err instanceof ApiError
            ? err.message
            : "Frühere Backtests konnten nicht geladen werden.",
      );
    } finally {
      setPastRunsLoading(false);
    }
  }, [strategy.id]);

  useEffect(() => {
    void loadPastRuns();
  }, [loadPastRuns]);

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    try {
      const overrideValues: Record<string, number> = {};
      for (const [name, raw] of Object.entries(overrides)) {
        const trimmed = raw.trim();
        if (trimmed === "") continue;
        const n = Number(trimmed);
        if (!Number.isNaN(n)) overrideValues[name] = n;
      }
      const run = await backtestStrategy(strategy.id, {
        start: start.trim() || undefined,
        end: end.trim() || undefined,
        overrides:
          Object.keys(overrideValues).length > 0 ? overrideValues : undefined,
        persist,
      });
      setActiveRun(run);
      // last_backtest_at/last_total_r auf der Summary aktuell halten, ohne
      // die ganze Strategie neu zu laden.
      setStrategy({
        ...strategy,
        last_backtest_at: run.created_at,
        last_total_r: run.metrics?.all.total_r ?? strategy.last_total_r,
      });
      void loadPastRuns();
    } catch (err) {
      setRunError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Backtest fehlgeschlagen.",
      );
    } finally {
      setRunning(false);
    }
  }

  async function handleLoadRun(runId: number) {
    setLoadingRunId(runId);
    try {
      const run = await getBacktest(runId);
      setActiveRun(run);
    } catch {
      // Non-fatal: der Run bleibt in der Liste, nur das Laden schlug fehl.
    } finally {
      setLoadingRunId(null);
    }
  }

  const trades = useMemo(
    () => (activeRun ? engineTradesToTrades(activeRun.trades) : []),
    [activeRun],
  );
  const rValues = useMemo(
    () => trades.map((t) => t.r_value).filter((r): r is number => r !== null),
    [trades],
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Run-Konfiguration */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bt-start">Start</Label>
            <Input
              id="bt-start"
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bt-end">Ende</Label>
            <Input
              id="bt-end"
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
          <div className="flex flex-col justify-end gap-1.5 pb-1.5">
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input
                type="checkbox"
                checked={persist}
                onChange={(e) => setPersist(e.target.checked)}
                className="size-4 rounded border-zinc-700 bg-zinc-900"
              />
              Ergebnis speichern (persist)
            </label>
          </div>
        </div>

        {paramEntries.length > 0 ? (
          <div className="mt-4 border-t border-zinc-800 pt-4">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Parameter-Overrides (leer = Default)
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {paramEntries.map(([name, spec]) => (
                <div key={name} className="flex flex-col gap-1.5">
                  <Label htmlFor={`ov-${name}`} title={spec.description ?? undefined}>
                    {name}
                  </Label>
                  <Input
                    id={`ov-${name}`}
                    type="number"
                    inputMode="decimal"
                    placeholder={String(spec.value)}
                    value={overrides[name] ?? ""}
                    onChange={(e) =>
                      setOverrides((prev) => ({ ...prev, [name]: e.target.value }))
                    }
                    className="font-mono"
                  />
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 flex items-center gap-3 border-t border-zinc-800 pt-4">
          <Button onClick={() => void handleRun()} disabled={running}>
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Play className="size-4" />
            )}
            Backtest ausführen
          </Button>
          {runError ? (
            <p className="text-sm text-red-400">{runError}</p>
          ) : null}
        </div>
      </div>

      {/* Aktuelles Ergebnis */}
      {activeRun ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400">
            <Badge
              variant="outline"
              className={cn(
                "font-normal",
                activeRun.status === "ok"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300",
              )}
            >
              {activeRun.status === "ok" ? "ok" : "failed"}
            </Badge>
            <span>Run #{activeRun.id}</span>
            <span className="text-zinc-700">·</span>
            <span>Version {activeRun.version}</span>
            <span className="text-zinc-700">·</span>
            <span>{fmtInt(activeRun.bars)} Bars</span>
            <span className="text-zinc-700">·</span>
            <span>{fmtDateTime(activeRun.created_at)}</span>
          </div>

          {activeRun.status === "failed" ? (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div>
                <p className="font-medium">Backtest fehlgeschlagen</p>
                <p className="mt-0.5 text-red-300/90">
                  {activeRun.error ?? "Unbekannter Fehler."}
                </p>
              </div>
            </div>
          ) : null}

          {/* Warnungen sind ehrliche Vorbehalte zum Ergebnis — nicht
              verstecken, sondern vor die Kennzahlen stellen. */}
          {activeRun.warnings.length > 0 ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
              <div className="flex items-center gap-2 font-medium">
                <AlertTriangle className="size-4 shrink-0" />
                {activeRun.warnings.length}{" "}
                {activeRun.warnings.length === 1 ? "Warnung" : "Warnungen"}
              </div>
              <ul className="mt-2 flex flex-col gap-1 pl-6 text-xs [list-style:disc]">
                {activeRun.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {activeRun.metrics ? (
            <section>
              <SectionTitle>Kennzahlen</SectionTitle>
              <MetricCards metrics={activeRun.metrics} />
            </section>
          ) : null}

          {trades.length > 0 ? (
            <section className="grid gap-4 lg:grid-cols-2">
              <div>
                <SectionTitle>R-Verteilung</SectionTitle>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
                  <RHistogram values={rValues} />
                </div>
              </div>
              <div>
                <SectionTitle>Equity-Kurve (kumuliertes R)</SectionTitle>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
                  <EquityCurve trades={trades} />
                </div>
              </div>
            </section>
          ) : null}
        </div>
      ) : (
        <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-sm text-zinc-500">
          Noch kein Backtest in dieser Sitzung ausgeführt.
        </div>
      )}

      {/* Frühere Backtests */}
      <section>
        <SectionTitle>Frühere Backtests</SectionTitle>
        {pastRunsLoading ? (
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="size-4 animate-spin" />
            Lade…
          </div>
        ) : pastRunsError ? (
          <p className="text-sm text-red-400">{pastRunsError}</p>
        ) : pastRuns.length === 0 ? (
          <p className="text-sm text-zinc-500">Noch keine Backtests gespeichert.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950 text-left text-zinc-400">
                  <th className="px-3 py-2 font-medium">Run</th>
                  <th className="px-3 py-2 font-medium">Version</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Bars</th>
                  <th className="px-3 py-2 text-right font-medium">Total R</th>
                  <th className="px-3 py-2 text-right font-medium">Warnungen</th>
                  <th className="px-3 py-2 font-medium">Erstellt</th>
                  <th className="px-3 py-2 text-right font-medium">
                    <span className="sr-only">Aktionen</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {pastRuns.map((r) => (
                  <tr key={r.id} className="border-b border-zinc-800/70 last:border-0">
                    <td className="px-3 py-2 font-mono text-zinc-300">#{r.id}</td>
                    <td className="px-3 py-2 font-mono text-zinc-400">v{r.version}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "font-normal",
                          r.status === "ok"
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                            : "border-red-500/30 bg-red-500/10 text-red-300",
                        )}
                      >
                        {r.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-400">
                      {fmtInt(r.bars)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">
                      {fmtR(r.metrics?.all.total_r ?? null)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-500">
                      {r.warnings.length > 0 ? r.warnings.length : "—"}
                    </td>
                    <td className="px-3 py-2 text-zinc-500">
                      {fmtDateTime(r.created_at)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleLoadRun(r.id)}
                        disabled={loadingRunId === r.id}
                        className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                      >
                        {loadingRunId === r.id ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : null}
                        Anzeigen
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// --------------------------------------------------------------------------
// Versions
// --------------------------------------------------------------------------

function VersionsPane({
  strategy,
  setStrategy,
}: {
  strategy: StrategyDetail;
  setStrategy: (s: StrategyDetail) => void;
}) {
  const [viewing, setViewing] = useState<number | null>(null);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const sorted = useMemo(
    () => [...strategy.versions].sort((a, b) => b.version - a.version),
    [strategy.versions],
  );

  async function handleRestore(version: StrategyVersion) {
    setRestoring(version.version);
    setRestoreError(null);
    try {
      const updated = await updateStrategy(strategy.id, {
        definition: version.definition,
        note: `Wiederhergestellt aus Version ${version.version}`,
      });
      setStrategy(updated);
    } catch (err) {
      setRestoreError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Wiederherstellen fehlgeschlagen.",
      );
    } finally {
      setRestoring(null);
    }
  }

  if (sorted.length === 0) {
    return (
      <p className="text-sm text-zinc-500">Keine Versionen vorhanden.</p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {restoreError ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {restoreError}
        </p>
      ) : null}

      {sorted.map((v) => {
        const isCurrent = v.version === strategy.current_version;
        const isOpen = viewing === v.version;
        return (
          <div
            key={v.version}
            className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/30"
          >
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <Badge
                variant="outline"
                className={cn(
                  "font-mono font-normal",
                  isCurrent && "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
                )}
              >
                v{v.version}
              </Badge>
              {isCurrent ? (
                <span className="text-xs text-emerald-400">aktuell</span>
              ) : null}
              <span className="text-xs text-zinc-500">
                {fmtDateTime(v.created_at)}
              </span>
              {v.note ? (
                <span className="text-sm text-zinc-300">{v.note}</span>
              ) : (
                <span className="text-sm text-zinc-600">ohne Notiz</span>
              )}
              <div className="ml-auto flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setViewing(isOpen ? null : v.version)}
                  className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                >
                  <History className="size-3.5" />
                  {isOpen ? "Ausblenden" : "Anzeigen"}
                </Button>
                {!isCurrent ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleRestore(v)}
                    disabled={restoring === v.version}
                    className="border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
                  >
                    {restoring === v.version ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RotateCcw className="size-3.5" />
                    )}
                    Wiederherstellen
                  </Button>
                ) : null}
              </div>
            </div>
            {isOpen ? (
              <div className="border-t border-zinc-800 p-3">
                <StrategyEditor
                  value={JSON.stringify(v.definition, null, 2)}
                  onChange={() => {}}
                  language="json"
                  height={320}
                  readOnly
                />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// --------------------------------------------------------------------------
// Trades
// --------------------------------------------------------------------------

function TradesPane({ activeRun }: { activeRun: BacktestRun | null }) {
  if (!activeRun) {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-sm text-zinc-500">
        Erst im Backtest-Tab einen Run ausführen oder aus „Frühere Backtests“
        laden.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm text-zinc-400">
        Run #{activeRun.id} · {fmtInt(activeRun.trades.length)} Trades
      </div>
      <EngineTradesTable trades={activeRun.trades} />
    </div>
  );
}
