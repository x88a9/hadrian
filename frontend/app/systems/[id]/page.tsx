"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Pencil, Plus, Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EquityCurve } from "@/components/equity-curve";
import { GradeBadge } from "@/components/grade-badge";
import { LiveMetricsCards } from "@/components/live-metrics-cards";
import { LiveTradesTable } from "@/components/live-trades-table";
import { MetricCards } from "@/components/metric-cards";
import { QuantSection } from "@/components/quant-section";
import { RHistogram } from "@/components/r-histogram";
import { RollingMetrics } from "@/components/rolling-metrics";
import { StatusSwitcher } from "@/components/status-switcher";
import { SystemConcepts } from "@/components/system-concepts";
import { SystemFormDialog } from "@/components/system-form-dialog";
import { TradeFormDialog } from "@/components/trade-form-dialog";
import { TradesTable } from "@/components/trades-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ApiError,
  deleteSystem,
  deleteTrade,
  getLiveMetrics,
  getLiveTrades,
  getSystem,
  getTrades,
} from "@/lib/api";
import type {
  LiveMetrics,
  LiveTrade,
  SystemDetail,
  Trade,
} from "@/lib/types";

function RuleCard({
  title,
  rule,
}: {
  title: string;
  rule: string | null;
}) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/30">
      <CardHeader>
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="max-w-prose whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
          {rule && rule.trim().length > 0 ? rule : "—"}
        </p>
      </CardContent>
    </Card>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

// Trennt die beiden Datenwelten der Seite sichtbar voneinander: real
// gehandelte Live-Trades oben, historische Backtest-Simulation darunter.
function DataDivider({
  label,
  hint,
  tone,
}: {
  label: string;
  hint: string;
  tone: "live" | "backtest";
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        className={
          tone === "live"
            ? "rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-cyan-300"
            : "rounded-md border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-zinc-400"
        }
      >
        {label}
      </span>
      <span className="text-xs text-zinc-600">{hint}</span>
      <span className="h-px flex-1 bg-zinc-800" />
    </div>
  );
}

export default function SystemDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [system, setSystem] = useState<SystemDetail | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ status: number; message: string } | null>(
    null,
  );
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [tradeDialogOpen, setTradeDialogOpen] = useState(false);
  const [tradeDialogMode, setTradeDialogMode] = useState<"create" | "edit">(
    "create",
  );
  const [editingTrade, setEditingTrade] = useState<Trade | undefined>(undefined);
  const [deletingTrade, setDeletingTrade] = useState<Trade | null>(null);

  // Phase 7: Live-Trades des Systems. Fehler hier sind nicht fatal — die
  // Backtest-Ansicht bleibt unberührt —, dürfen aber nicht als „keine
  // Live-Trades" durchgehen, sonst wirkt der Abschnitt schlicht leer.
  const [liveTrades, setLiveTrades] = useState<LiveTrade[]>([]);
  const [liveMetrics, setLiveMetrics] = useState<LiveMetrics | null>(null);
  const [liveLoading, setLiveLoading] = useState(true);
  const [liveError, setLiveError] = useState<string | null>(null);

  // Daten laden (auch nach Mutationen erneut aufrufbar).
  const reload = useCallback(async () => {
    try {
      const [sys, tradesRes] = await Promise.all([
        getSystem(Number(id)),
        getTrades({ system_id: Number(id), limit: 10000 }),
      ]);
      setSystem(sys);
      setTrades(tradesRes.items);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ status: err.status, message: err.message });
      } else {
        setError({
          status: 0,
          message: err instanceof Error ? err.message : "Unbekannter Fehler",
        });
      }
    }
  }, [id]);

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

  // Live-Trades separat laden — unabhängig vom Backtest-Ladepfad.
  useEffect(() => {
    let active = true;
    setLiveLoading(true);
    setLiveError(null);
    Promise.all([
      getLiveTrades({ system_id: Number(id), include_cancelled: true }),
      getLiveMetrics(Number(id)),
    ])
      .then(([tradesRes, metrics]) => {
        if (!active) return;
        setLiveTrades(tradesRes.items);
        setLiveMetrics(metrics);
      })
      .catch((err) => {
        if (!active) return;
        setLiveTrades([]);
        setLiveMetrics(null);
        setLiveError(
          err instanceof ApiError && err.status === 0
            ? "Backend nicht erreichbar."
            : err instanceof ApiError
              ? err.message
              : "Unbekannter Fehler.",
        );
      })
      .finally(() => {
        if (active) setLiveLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  const rValues = useMemo(
    () =>
      trades
        .map((t) => t.r_value)
        .filter((r): r is number => typeof r === "number" && !Number.isNaN(r)),
    [trades],
  );

  return (
    <div className="flex flex-col gap-8 py-4">
      <Link
        href="/systems"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-300"
      >
        <ArrowLeft className="size-4" />
        Zurück zur Übersicht
      </Link>

      {loading && (
        <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
          Lade System #{id} …
        </div>
      )}

      {!loading && error && (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardHeader>
            <div className="mb-1 flex size-10 items-center justify-center rounded-md border border-red-900/50 bg-red-950/40 text-red-400">
              <AlertTriangle className="size-5" />
            </div>
            <CardTitle className="text-red-200">
              {error.status === 404
                ? `System #${id} nicht gefunden`
                : "System konnte nicht geladen werden"}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-red-300/80">
            {error.status === 0
              ? "Backend nicht erreichbar. Läuft das API (docker compose up)?"
              : error.message}
          </CardContent>
        </Card>
      )}

      {!loading && !error && system && (
        <>
          {/* Header */}
          <header className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight text-zinc-50">
                {system.name}
              </h1>
              <GradeBadge
                grade={system.metrics.all.composite_grade}
                className="h-6 px-2 text-sm"
              />
              {system.origin === "ui" ? (
                <Badge
                  variant="outline"
                  title="In der UI angelegt (Re-Import-geschützt)"
                  className="font-normal bg-sky-500/10 text-sky-300 border-sky-500/30"
                >
                  ui
                </Badge>
              ) : null}
              <div className="ml-auto flex items-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => setEditOpen(true)}
                  className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                >
                  <Pencil className="size-4" />
                  Bearbeiten
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setDeleteOpen(true)}
                  className="border-red-500/30 bg-transparent text-red-400/90 hover:bg-red-500/10 hover:text-red-300"
                >
                  <Trash2 className="size-4" />
                  Löschen
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <StatusSwitcher
                systemId={system.id}
                status={system.status}
                onChanged={() => void reload()}
              />
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                <span>Prefix {system.prefix}</span>
                <span className="text-zinc-700">·</span>
                <span>{system.timeframe}</span>
                <span className="text-zinc-700">·</span>
                {system.asset ? (
                  <span className="inline-flex items-center rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 font-mono text-zinc-300">
                    {system.asset}
                  </span>
                ) : (
                  <span className="text-zinc-600">kein Asset</span>
                )}
              </div>
            </div>

            <SystemFormDialog
              open={editOpen}
              onOpenChange={setEditOpen}
              mode="edit"
              system={system}
              onSaved={() => void reload()}
            />

            <ConfirmDialog
              open={deleteOpen}
              onOpenChange={setDeleteOpen}
              title={`System „${system.name}" löschen?`}
              description={
                <>
                  Löscht das System unwiderruflich, inklusive{" "}
                  <span className="font-medium text-zinc-300">
                    {trades.length}{" "}
                    {trades.length === 1 ? "Trade" : "Trades"}
                  </span>
                  , zugehöriger Parameter-Sweeps und Konzept-Zuordnungen.
                </>
              }
              confirmLabel="Endgültig löschen"
              destructive
              onConfirm={async () => {
                await deleteSystem(system.id);
                router.push("/systems");
              }}
            />
            {system.import_status === "incomplete" && (
              <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
                <AlertTriangle className="size-4 shrink-0" />
                Backtest unvollständig — Kennzahlen ggf. nicht aussagekräftig.
              </div>
            )}
          </header>

          {/* Regel-Briefing */}
          <section>
            <SectionTitle>Regel-Briefing</SectionTitle>
            <div className="grid gap-3 md:grid-cols-3">
              <RuleCard title="Entry" rule={system.entry_rule} />
              <RuleCard title="Stop Loss" rule={system.sl_rule} />
              <RuleCard title="Take Profit" rule={system.tp_rule} />
            </div>
            {system.notes && system.notes.trim().length > 0 && (
              <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
                <div className="mb-1 text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Notizen
                </div>
                <p className="max-w-prose whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
                  {system.notes}
                </p>
              </div>
            )}
          </section>

          {/* Konzepte */}
          <section>
            <SectionTitle>Konzepte</SectionTitle>
            <SystemConcepts systemId={system.id} />
          </section>

          {/* --- Livetesting-Daten (real) — immer sichtbar, auch leer --- */}
          <DataDivider
            tone="live"
            label="Livetesting-Daten"
            hint="Real gehandelt — Kontostand-wirksam"
          />
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <SectionTitle>Live (real)</SectionTitle>
              <Button
                size="sm"
                variant="outline"
                className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                render={<Link href={`/live/new?system=${system.id}`} />}
              >
                <Plus className="size-4" />
                Live-Trade anlegen
              </Button>
            </div>
            {liveError ? (
              <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                <AlertTriangle className="size-4 shrink-0" />
                Live-Daten konnten nicht geladen werden ({liveError}) — der
                Abschnitt ist deshalb leer, nicht zwingend das System.
              </div>
            ) : liveLoading ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 px-4 py-8 text-center text-sm text-zinc-500">
                Lade Live-Trades …
              </div>
            ) : liveTrades.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-10 text-center">
                <p className="text-sm font-medium text-zinc-300">
                  Noch keine Live-Trades für dieses System.
                </p>
                <p className="max-w-md text-sm text-zinc-500">
                  Sobald das System real gehandelt wird, stehen hier die
                  Live-Kennzahlen neben den Backtest-Werten.
                </p>
                <Link
                  href={`/live/new?system=${system.id}`}
                  className="mt-1 text-sm text-sky-400 transition-colors hover:text-sky-300"
                >
                  Ersten Live-Trade anlegen →
                </Link>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {liveMetrics ? <LiveMetricsCards metrics={liveMetrics} /> : null}
                <LiveTradesTable trades={liveTrades} />
              </div>
            )}
          </section>

          {/* --- Backtest-Daten — historische Simulation --- */}
          <DataDivider
            tone="backtest"
            label="Backtest-Daten"
            hint="Historische Simulation — nicht real gehandelt"
          />

          {/* Kennzahlen */}
          <section>
            <SectionTitle>Kennzahlen (Backtest)</SectionTitle>
            <MetricCards metrics={system.metrics} />
          </section>

          {/* Charts */}
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
                <EquityCurve
                  trades={trades}
                  splitDate={system.split_date ?? null}
                />
              </div>
            </div>
          </section>

          {/* Rolling EV */}
          <section>
            <SectionTitle>Rolling EV</SectionTitle>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
              <RollingMetrics trades={trades} />
            </div>
          </section>

          {/* Quant-Analytik (Topographie / Walk-Forward / Monte-Carlo) */}
          <QuantSection systemId={system.id} trades={trades} />

          {/* Trades */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <SectionTitle>Backtest-Trades ({trades.length})</SectionTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setTradeDialogMode("create");
                  setEditingTrade(undefined);
                  setTradeDialogOpen(true);
                }}
                className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
              >
                <Plus className="size-4" />
                Trade hinzufügen
              </Button>
            </div>
            <TradesTable
              trades={trades}
              onEdit={(t) => {
                setTradeDialogMode("edit");
                setEditingTrade(t);
                setTradeDialogOpen(true);
              }}
              onDelete={(t) => setDeletingTrade(t)}
            />
          </section>

          <TradeFormDialog
            open={tradeDialogOpen}
            onOpenChange={setTradeDialogOpen}
            mode={tradeDialogMode}
            systemId={system.id}
            defaultTimeframe={system.timeframe}
            trade={editingTrade}
            onSaved={() => void reload()}
          />

          <ConfirmDialog
            open={deletingTrade !== null}
            onOpenChange={(next) => {
              if (!next) setDeletingTrade(null);
            }}
            title="Trade löschen?"
            description={
              <>
                Löscht diesen Trade unwiderruflich. Die Kennzahlen werden neu
                berechnet.
                {deletingTrade && deletingTrade.source !== "ui" ? (
                  <span className="mt-2 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-300">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    Importierter Trade (source={deletingTrade.source}) — wird
                    beim nächsten Re-Import ohnehin ersetzt.
                  </span>
                ) : null}
              </>
            }
            confirmLabel="Endgültig löschen"
            destructive
            onConfirm={async () => {
              if (!deletingTrade) return;
              await deleteTrade(deletingTrade.id);
              setDeletingTrade(null);
              await reload();
            }}
          />
        </>
      )}
    </div>
  );
}
