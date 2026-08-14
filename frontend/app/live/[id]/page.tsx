"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  Loader2,
  Pencil,
  Timer,
  Trash2,
} from "lucide-react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { LiveStageBadge } from "@/components/live-stage-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  deleteLiveTrade,
  getLiveTrade,
  transitionLiveTrade,
  updateLiveTrade,
} from "@/lib/api";
import { fmtNum, fmtPct, fmtR } from "@/lib/format";
import {
  STAGE_LABEL,
  STAGE_ORDER,
  fmtDuration,
  fmtPctValue,
  fmtUsd,
  durationSince,
  NEXT_STAGES,
  OPEN_STAGES,
  stageColor,
  winLossColor,
} from "@/lib/live-format";
import { cn } from "@/lib/utils";
import type {
  EntryOrderType,
  LiveStage,
  LiveTrade,
  LiveTradeUpdatePayload,
  LiveWinLoss,
  TransitionPayload,
} from "@/lib/types";

const PLACEHOLDER = "—";

function num(value: string): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

// Zeitstempel-Feld je Lebenszyklus-Stufe (STAGE_ORDER).
const STAGE_TIMESTAMP: Record<LiveStage, keyof LiveTrade> = {
  setup_sighted: "setup_sighted_at",
  risk_calculated: "risk_calculated_at",
  order_placed: "order_placed_at",
  entry_filled: "entry_filled_at",
  running: "running_at",
  closed: "closed_at",
  cancelled: "cancelled_at",
};

// base-ui rendert in <Select.Value> den rohen value, solange dem Root kein
// `items`-Mapping gegeben wird (siehe SelectRoot.Props.items).
const ORDER_TYPE_ITEMS: Record<string, string> = {
  market: "Market",
  limit: "Limit",
};

const WIN_LOSS_LABEL: Record<LiveWinLoss, string> = {
  win: "Win",
  loss: "Loss",
  break_even: "Break-even",
};

// Datum + Uhrzeit inkl. Sekunden (deterministisch, ohne Locale/TZ).
function fmtStamp(iso: string | null | undefined): string {
  if (!iso) return PLACEHOLDER;
  const m = iso.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/,
  );
  if (!m) return PLACEHOLDER;
  const [, y, mo, d, hh, mm, ss] = m;
  if (hh === undefined) return `${y}-${mo}-${d}`;
  return `${y}-${mo}-${d} ${hh}:${mm}${ss ? `:${ss}` : ""}`;
}

function Field({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  accent?: string;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-xs text-zinc-500">
        {label}
        {hint ? (
          <span className="ml-1 text-[10px] text-zinc-600">({hint})</span>
        ) : null}
      </span>
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

function StageTimeline({ trade }: { trade: LiveTrade }) {
  const cancelled = trade.stage === "cancelled";
  const currentIdx = STAGE_ORDER.indexOf(trade.stage);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-stretch gap-2">
        {STAGE_ORDER.map((stage) => {
          const ts = trade[STAGE_TIMESTAMP[stage]] as string | null;
          const reached = ts !== null && ts !== undefined;
          const isCurrent = !cancelled && stage === trade.stage;
          const future = !reached && !isCurrent;
          return (
            <div
              key={stage}
              className={cn(
                "flex min-w-[8.5rem] flex-1 flex-col gap-1 rounded-md border px-3 py-2 transition-colors",
                reached || isCurrent
                  ? stageColor(stage)
                  : "border-zinc-800 bg-zinc-900/20 text-zinc-600",
                isCurrent && "ring-1 ring-inset ring-current",
                future && "opacity-60",
              )}
              aria-current={isCurrent ? "step" : undefined}
            >
              <span className="text-xs font-medium">{STAGE_LABEL[stage]}</span>
              <span className="font-mono text-[11px] tabular-nums opacity-80">
                {reached ? fmtStamp(ts) : PLACEHOLDER}
              </span>
            </div>
          );
        })}
      </div>
      {cancelled ? (
        <div
          className={cn(
            "flex items-center gap-2 rounded-md border px-3 py-2 text-xs",
            stageColor("cancelled"),
          )}
        >
          <AlertTriangle className="size-3.5 shrink-0 no-underline" />
          <span className="no-underline">
            Abgebrochen bei Stufe #{currentIdx + 1} —{" "}
            <span className="font-mono tabular-nums">
              {fmtStamp(trade.cancelled_at)}
            </span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

// Ab dieser Abweichung zwischen geplantem und tatsaechlichem Entry/Stop wird
// gewarnt. Nicht blockierend — echte Slippage kann gross sein —, aber der
// haeufigste Fehler ist ein versehentlich angehaengter statt ersetzter Wert
// (109000 + 108990 -> 109000108990), und der faellt hier sofort auf.
const DEVIATION_WARN_PCT = 5;

// Abweichung in % (null, wenn nicht berechenbar).
function deviationPct(
  planned: number | null | undefined,
  actual: number | null,
): number | null {
  if (planned === null || planned === undefined || planned === 0) return null;
  if (actual === null) return null;
  return ((actual - planned) / planned) * 100;
}

function DeviationWarning({
  label,
  planned,
  actual,
  pct,
}: {
  label: string;
  planned: number;
  actual: number;
  pct: number;
}) {
  return (
    <div className="flex w-full items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-0.5">
        <p className="font-medium">
          {label} weicht {Math.abs(pct).toFixed(1)} % vom Plan ab — bitte
          prüfen.
        </p>
        <p className="font-mono tabular-nums">
          geplant {fmtNum(planned, 4)} → eingegeben {fmtNum(actual, 4)} (
          {pct >= 0 ? "+" : "−"}
          {Math.abs(pct).toFixed(1)} %)
        </p>
        <p>
          Tippfehler? Das Feld ist mit dem Plan vorbefüllt — der neue Wert muss
          ihn ersetzen, nicht ergänzen.
        </p>
      </div>
    </div>
  );
}

function TransitionPanel({
  trade,
  onDone,
}: {
  trade: LiveTrade;
  onDone: () => Promise<void>;
}) {
  const targets = NEXT_STAGES[trade.stage];
  const [pending, setPending] = useState<LiveStage | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Lokaler Formular-Zustand je Übergangstyp.
  const [orderType, setOrderType] = useState<EntryOrderType>(
    trade.entry_order_type ?? "limit",
  );
  const [actualEntry, setActualEntry] = useState<string>(
    trade.planned_entry !== null ? String(trade.planned_entry) : "",
  );
  const [actualStop, setActualStop] = useState<string>(
    trade.planned_stop !== null ? String(trade.planned_stop) : "",
  );
  const [exitPrice, setExitPrice] = useState("");
  const [realizedPnl, setRealizedPnl] = useState("");
  const [feesPaid, setFeesPaid] = useState("");
  const [fundingPaid, setFundingPaid] = useState("");
  const [rulesFollowed, setRulesFollowed] = useState(true);
  const [closeOpen, setCloseOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelNote, setCancelNote] = useState("");
  const [fillOpen, setFillOpen] = useState(false);

  // Plausibilitaet der Ausfuehrungs-Eingaben (nur Warnung, kein Blocker).
  const entryDev = deviationPct(trade.planned_entry, num(actualEntry));
  const stopDev = deviationPct(trade.planned_stop, num(actualStop));
  const entryWarn = entryDev !== null && Math.abs(entryDev) > DEVIATION_WARN_PCT;
  const stopWarn = stopDev !== null && Math.abs(stopDev) > DEVIATION_WARN_PCT;
  const fillWarn = entryWarn || stopWarn;

  const fillPayload = (): TransitionPayload => ({
    target_stage: "entry_filled",
    actual_entry: num(actualEntry),
    actual_stop: num(actualStop),
  });

  function toMessage(err: unknown): string {
    if (err instanceof ApiError) {
      return err.status === 0 ? "Backend nicht erreichbar." : err.message;
    }
    return err instanceof Error ? err.message : "Übergang fehlgeschlagen.";
  }

  async function run(target: LiveStage, payload: TransitionPayload) {
    setPending(target);
    setError(null);
    try {
      await transitionLiveTrade(trade.id, payload);
      await onDone();
    } catch (err) {
      setError(toMessage(err));
    } finally {
      setPending(null);
    }
  }

  if (targets.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        Terminale Stufe — kein weiterer Übergang möglich.
      </p>
    );
  }

  const busy = pending !== null;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {targets.includes("risk_calculated") ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <span className="text-sm text-zinc-400">Risk (neu) berechnen</span>
          <Button
            className="ml-auto"
            disabled={busy}
            onClick={() => void run("risk_calculated", { target_stage: "risk_calculated" })}
          >
            {pending === "risk_calculated" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : null}
            Neu berechnen
          </Button>
        </div>
      ) : null}

      {targets.includes("order_placed") ? (
        <div className="flex flex-wrap items-end gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="flex flex-col gap-1.5">
            <Label>Order-Typ</Label>
            <Select
              items={ORDER_TYPE_ITEMS}
              value={orderType}
              onValueChange={(v) => setOrderType(v as EntryOrderType)}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="market">Market</SelectItem>
                <SelectItem value="limit">Limit</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            className="ml-auto"
            disabled={busy}
            onClick={() =>
              void run("order_placed", {
                target_stage: "order_placed",
                entry_order_type: orderType,
              })
            }
          >
            {pending === "order_placed" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : null}
            Order gesetzt
          </Button>
        </div>
      ) : null}

      {targets.includes("entry_filled") ? (
        <div className="flex flex-wrap items-end gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tr-actual-entry">Tatsächlicher Entry</Label>
            <Input
              id="tr-actual-entry"
              type="number"
              inputMode="decimal"
              className={cn(
                "w-36 font-mono tabular-nums",
                entryWarn && "border-amber-500/60 text-amber-200",
              )}
              value={actualEntry}
              // Vorbefuellter Plan-Wert: markieren, damit Tippen ihn ERSETZT
              // statt anzuhaengen.
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setActualEntry(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tr-actual-stop">Tatsächlicher Stop (optional)</Label>
            <Input
              id="tr-actual-stop"
              type="number"
              inputMode="decimal"
              className={cn(
                "w-36 font-mono tabular-nums",
                stopWarn && "border-amber-500/60 text-amber-200",
              )}
              value={actualStop}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setActualStop(e.target.value)}
            />
          </div>
          {entryWarn && entryDev !== null ? (
            <DeviationWarning
              label="Entry"
              planned={trade.planned_entry as number}
              actual={num(actualEntry) as number}
              pct={entryDev}
            />
          ) : null}
          {stopWarn && stopDev !== null ? (
            <DeviationWarning
              label="Stop"
              planned={trade.planned_stop as number}
              actual={num(actualStop) as number}
              pct={stopDev}
            />
          ) : null}
          <Button
            className={cn(
              "ml-auto",
              fillWarn &&
                "border border-amber-500/50 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25",
            )}
            disabled={busy}
            onClick={() => {
              // Normalfall: direkt weiter. Bei Warnung ein Bestaetigungsschritt,
              // damit ein versehentlicher Klick auffaellt.
              if (fillWarn) {
                setError(null);
                setFillOpen(true);
                return;
              }
              void run("entry_filled", fillPayload());
            }}
          >
            {pending === "entry_filled" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : null}
            {fillWarn ? "Entry gefüllt (trotz Abweichung)" : "Entry gefüllt"}
          </Button>
          <ConfirmDialog
            open={fillOpen}
            onOpenChange={setFillOpen}
            title="Abweichende Ausführung bestätigen?"
            description={
              <span className="flex flex-col gap-2">
                {entryWarn && entryDev !== null ? (
                  <span className="font-mono text-xs tabular-nums">
                    Entry: geplant {fmtNum(trade.planned_entry, 4)} →
                    eingegeben {fmtNum(num(actualEntry), 4)} (
                    {entryDev >= 0 ? "+" : "−"}
                    {Math.abs(entryDev).toFixed(1)} %)
                  </span>
                ) : null}
                {stopWarn && stopDev !== null ? (
                  <span className="font-mono text-xs tabular-nums">
                    Stop: geplant {fmtNum(trade.planned_stop, 4)} → eingegeben{" "}
                    {fmtNum(num(actualStop), 4)} ({stopDev >= 0 ? "+" : "−"}
                    {Math.abs(stopDev).toFixed(1)} %)
                  </span>
                ) : null}
                <span>
                  Diese Werte bestimmen Risiko, R-Wert und Ausführungsqualität.
                  Nur bestätigen, wenn die Slippage wirklich so groß war.
                </span>
              </span>
            }
            confirmLabel="Werte sind korrekt"
            destructive
            onConfirm={async () => {
              await transitionLiveTrade(trade.id, fillPayload());
              await onDone();
            }}
          />
        </div>
      ) : null}

      {targets.includes("running") ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <span className="text-sm text-zinc-400">
            Position läuft — als laufend markieren
          </span>
          <Button
            className="ml-auto"
            disabled={busy}
            onClick={() => void run("running", { target_stage: "running" })}
          >
            {pending === "running" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : null}
            Laufend
          </Button>
        </div>
      ) : null}

      {targets.includes("closed") ? (
        <div className="flex flex-col gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-exit">Exit-Preis</Label>
              <Input
                id="tr-exit"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={exitPrice}
                onChange={(e) => setExitPrice(e.target.value)}
                placeholder="Preis ODER PnL"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-pnl">Realisierter PnL ($)</Label>
              <Input
                id="tr-pnl"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={realizedPnl}
                onChange={(e) => setRealizedPnl(e.target.value)}
                placeholder="Preis ODER PnL"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-fees">Fees ($, optional)</Label>
              <Input
                id="tr-fees"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={feesPaid}
                onChange={(e) => setFeesPaid(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-funding">Funding ($, optional)</Label>
              <Input
                id="tr-funding"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={fundingPaid}
                onChange={(e) => setFundingPaid(e.target.value)}
              />
            </div>
          </div>
          <label className="flex w-fit items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              className="size-4 accent-emerald-500"
              checked={rulesFollowed}
              onChange={(e) => setRulesFollowed(e.target.checked)}
            />
            Regeln befolgt
          </label>
          <Button
            className="ml-auto border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
            disabled={busy}
            onClick={() => {
              setError(null);
              setCloseOpen(true);
            }}
          >
            Trade schließen
          </Button>
          <ConfirmDialog
            open={closeOpen}
            onOpenChange={setCloseOpen}
            title="Trade schließen?"
            description="Schließt die Position, berechnet PnL/R und aktualisiert den Kontostand. Nicht umkehrbar."
            confirmLabel="Schließen"
            onConfirm={async () => {
              const exit = num(exitPrice);
              const pnl = num(realizedPnl);
              if (exit === null && pnl === null) {
                throw new Error(
                  "Exit-Preis ODER realisierter PnL ist erforderlich.",
                );
              }
              const payload: TransitionPayload = {
                target_stage: "closed",
                rules_followed: rulesFollowed,
              };
              if (exit !== null) payload.exit_price = exit;
              if (pnl !== null) payload.realized_pnl_usd = pnl;
              if (num(feesPaid) !== null) payload.fees_paid = num(feesPaid);
              if (num(fundingPaid) !== null) {
                payload.funding_paid = num(fundingPaid);
              }
              await transitionLiveTrade(trade.id, payload);
              await onDone();
            }}
          />
        </div>
      ) : null}

      {targets.includes("cancelled") ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-red-500/20 bg-red-500/[0.04] p-3">
          <span className="text-sm text-zinc-400">
            Trade vor Entry abbrechen
          </span>
          <Button
            variant="outline"
            className="ml-auto border-red-500/30 bg-transparent text-red-400/90 hover:bg-red-500/10 hover:text-red-300"
            disabled={busy}
            onClick={() => {
              setError(null);
              setCancelOpen(true);
            }}
          >
            Abbrechen
          </Button>
          <ConfirmDialog
            open={cancelOpen}
            onOpenChange={setCancelOpen}
            title="Trade abbrechen?"
            description={
              <span className="flex flex-col gap-2">
                <span>
                  Bricht den Trade ab. Nur vor gefülltem Entry möglich.
                </span>
                <Textarea
                  value={cancelNote}
                  onChange={(e) => setCancelNote(e.target.value)}
                  placeholder="Grund (optional)"
                  rows={2}
                />
              </span>
            }
            confirmLabel="Abbrechen bestätigen"
            destructive
            onConfirm={async () => {
              await transitionLiveTrade(trade.id, {
                target_stage: "cancelled",
                note: cancelNote.trim() || null,
              });
              await onDone();
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

// Ab dieser Stufe ist die Ausfuehrung dokumentiert und damit korrigierbar.
const CORRECTABLE_STAGES: LiveStage[] = ["entry_filled", "running", "closed"];

function numStr(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

// „Ausfuehrung korrigieren“ (PATCH /live-trades/{id}). Nachtraegliches
// Richtigstellen falsch getippter Ausfuehrungswerte, ohne den Trade loeschen
// und neu anlegen zu muessen.
function CorrectionPanel({
  trade,
  onDone,
}: {
  trade: LiveTrade;
  onDone: () => Promise<void>;
}) {
  const closed = trade.stage === "closed";

  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState(() => numStr(trade.actual_entry));
  const [stop, setStop] = useState(() => numStr(trade.actual_stop));
  const [exit, setExit] = useState(() => numStr(trade.exit_price));
  const [fees, setFees] = useState(() => numStr(trade.fees_paid));
  const [funding, setFunding] = useState(() => numStr(trade.funding_paid));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Serverstand nach jedem Reload uebernehmen.
  useEffect(() => {
    setEntry(numStr(trade.actual_entry));
    setStop(numStr(trade.actual_stop));
    setExit(numStr(trade.exit_price));
    setFees(numStr(trade.fees_paid));
    setFunding(numStr(trade.funding_paid));
    setError(null);
  }, [
    trade.id,
    trade.actual_entry,
    trade.actual_stop,
    trade.exit_price,
    trade.fees_paid,
    trade.funding_paid,
  ]);

  const payload: LiveTradeUpdatePayload = {};
  if (num(entry) !== trade.actual_entry) payload.actual_entry = num(entry);
  if (num(stop) !== trade.actual_stop) payload.actual_stop = num(stop);
  if (closed) {
    if (num(exit) !== trade.exit_price) payload.exit_price = num(exit);
    if (num(fees) !== trade.fees_paid) payload.fees_paid = num(fees);
    if (num(funding) !== trade.funding_paid) {
      payload.funding_paid = num(funding);
    }
  }
  const dirty = Object.keys(payload).length > 0;

  const entryDev = deviationPct(trade.planned_entry, num(entry));
  const entryWarn = entryDev !== null && Math.abs(entryDev) > DEVIATION_WARN_PCT;

  async function save() {
    setPending(true);
    setError(null);
    try {
      await updateLiveTrade(trade.id, payload);
      await onDone();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : "Korrektur fehlgeschlagen.",
      );
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <Button
        variant="outline"
        className="w-fit border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
        onClick={() => setOpen(true)}
      >
        <Pencil className="size-4" />
        Ausführung korrigieren
      </Button>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
      {closed ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            Dieser Trade ist geschlossen. Eine Korrektur berechnet PnL, R-Wert,
            Ergebnis und Ausführungsqualität <strong>und den Kontostand</strong>{" "}
            neu.
          </span>
        </div>
      ) : (
        <p className="text-xs text-zinc-500">
          Korrigiert die dokumentierte Ausführung. Wirkt sich auf Risiko,
          R-Wert und Ausführungsqualität aus.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="co-entry">Tatsächlicher Entry</Label>
          <Input
            id="co-entry"
            type="number"
            inputMode="decimal"
            className={cn(
              "font-mono tabular-nums",
              entryWarn && "border-amber-500/60 text-amber-200",
            )}
            value={entry}
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setEntry(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="co-stop">Tatsächlicher Stop</Label>
          <Input
            id="co-stop"
            type="number"
            inputMode="decimal"
            className="font-mono tabular-nums"
            value={stop}
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setStop(e.target.value)}
          />
        </div>
        {closed ? (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="co-exit">Exit-Preis</Label>
              <Input
                id="co-exit"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={exit}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setExit(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="co-fees">Fees ($)</Label>
              <Input
                id="co-fees"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={fees}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setFees(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="co-funding">Funding ($)</Label>
              <Input
                id="co-funding"
                type="number"
                inputMode="decimal"
                className="font-mono tabular-nums"
                value={funding}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setFunding(e.target.value)}
              />
            </div>
          </>
        ) : null}
      </div>

      {entryWarn && entryDev !== null ? (
        <DeviationWarning
          label="Entry"
          planned={trade.planned_entry as number}
          actual={num(entry) as number}
          pct={entryDev}
        />
      ) : null}

      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
          disabled={pending}
          onClick={() => {
            setEntry(numStr(trade.actual_entry));
            setStop(numStr(trade.actual_stop));
            setExit(numStr(trade.exit_price));
            setFees(numStr(trade.fees_paid));
            setFunding(numStr(trade.funding_paid));
            setError(null);
            setOpen(false);
          }}
        >
          Verwerfen
        </Button>
        <Button
          disabled={pending || !dirty}
          onClick={() => {
            // Geschlossener Trade: Kontostand haengt dran -> Rueckfrage.
            if (closed) {
              setError(null);
              setConfirmOpen(true);
              return;
            }
            void save();
          }}
        >
          {pending ? <Loader2 className="size-4 animate-spin" /> : null}
          Korrektur speichern
        </Button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Geschlossenen Trade korrigieren?"
        description="Kennzahlen (PnL, R-Wert, Ergebnis, Abweichung) und der Kontostand werden aus den neuen Werten neu berechnet."
        confirmLabel="Neu berechnen"
        destructive
        onConfirm={async () => {
          await updateLiveTrade(trade.id, payload);
          await onDone();
        }}
      />
    </div>
  );
}

function NotesEditor({
  trade,
  onSaved,
}: {
  trade: LiveTrade;
  onSaved: (t: LiveTrade) => void;
}) {
  const [value, setValue] = useState(trade.notes ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bei Trade-Reload aktuellen Serverstand übernehmen.
  useEffect(() => {
    setValue(trade.notes ?? "");
  }, [trade.id, trade.notes]);

  const dirty = value !== (trade.notes ?? "");

  async function save() {
    setPending(true);
    setError(null);
    try {
      const updated = await updateLiveTrade(trade.id, {
        notes: value.trim() ? value : null,
      });
      onSaved(updated);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : "Speichern fehlgeschlagen.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Beobachtungen, Kontext, Nachbereitung…"
        rows={4}
      />
      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={pending || !dirty}>
          {pending ? <Loader2 className="size-4 animate-spin" /> : null}
          Speichern
        </Button>
      </div>
    </div>
  );
}

export default function LiveTradeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [trade, setTrade] = useState<LiveTrade | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ status: number; message: string } | null>(
    null,
  );
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  const reload = useCallback(async () => {
    try {
      const t = await getLiveTrade(Number(id));
      setTrade(t);
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

  // Live-Laufzeit für offene Positionen aktuell halten.
  useEffect(() => {
    if (!trade || !OPEN_STAGES.includes(trade.stage)) return;
    const handle = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(handle);
  }, [trade]);

  const isOpen = trade ? OPEN_STAGES.includes(trade.stage) : false;

  return (
    <div className="flex flex-col gap-8 py-4">
      <Link
        href="/live"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-300"
      >
        <ArrowLeft className="size-4" />
        Zurück zu Live-Trading
      </Link>

      {loading ? (
        <div className="flex h-64 items-center justify-center gap-2 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Lade Trade #{id} …
        </div>
      ) : null}

      {!loading && error ? (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardHeader>
            <div className="mb-1 flex size-10 items-center justify-center rounded-md border border-red-900/50 bg-red-950/40 text-red-400">
              <AlertTriangle className="size-5" />
            </div>
            <CardTitle className="text-red-200">
              {error.status === 404
                ? `Trade #${id} nicht gefunden`
                : "Trade konnte nicht geladen werden"}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-red-300/80">
            {error.status === 0
              ? "Backend nicht erreichbar. Läuft das API (docker compose up)?"
              : error.message}
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error && trade ? (
        <>
          {/* Kopf */}
          <header className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
                {trade.system_id === null
                  ? "Freier Trade"
                  : (trade.system_name ?? `System #${trade.system_id}`)}
              </h1>
              {trade.system_id !== null ? (
                <Link
                  href={`/systems/${trade.system_id}`}
                  className="text-xs text-sky-400 transition-colors hover:text-sky-300"
                >
                  System öffnen
                </Link>
              ) : (
                <span className="rounded-md border border-zinc-800 bg-zinc-900/40 px-2 py-0.5 text-xs text-zinc-500">
                  ohne System-Zuordnung
                </span>
              )}
              {trade.asset ? (
                <span className="rounded-md border border-zinc-800 bg-zinc-900/40 px-2 py-0.5 font-mono text-xs text-zinc-300">
                  {trade.asset}
                </span>
              ) : null}
              <LiveStageBadge stage={trade.stage} />
              {trade.direction ? (
                <span
                  className={cn(
                    "rounded-md border px-2 py-0.5 text-xs font-medium",
                    trade.direction === "long"
                      ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                      : "border-red-500/30 bg-red-500/15 text-red-400",
                  )}
                >
                  {trade.direction === "long" ? "Long" : "Short"}
                </span>
              ) : null}
              {isOpen ? (
                <span className="inline-flex items-center gap-1.5 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs text-cyan-300">
                  <Timer className="size-3.5" />
                  {fmtDuration(
                    durationSince(
                      trade.entry_filled_at ?? trade.opened_at,
                      nowMs,
                    ),
                  )}
                </span>
              ) : null}
              {trade.chart_url ? (
                <a
                  href={trade.chart_url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto inline-flex items-center gap-1 text-xs text-zinc-400 transition-colors hover:text-zinc-200"
                >
                  <ExternalLink className="size-3.5" />
                  Chart
                </a>
              ) : null}
            </div>
          </header>

          {/* Stage-Timeline */}
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Lebenszyklus
            </h2>
            <StageTimeline trade={trade} />
          </section>

          {/* Karten */}
          <section className="grid gap-4 lg:grid-cols-3">
            <Card className="border-zinc-800 bg-zinc-900/30">
              <CardHeader>
                <CardTitle className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Plan
                </CardTitle>
              </CardHeader>
              <CardContent className="divide-y divide-zinc-800/60">
                <Field
                  label="Geplanter Entry"
                  value={fmtNum(trade.planned_entry, 4)}
                />
                <Field
                  label="Geplanter Stop"
                  value={fmtNum(trade.planned_stop, 4)}
                />
                <Field
                  label="Order-Typ"
                  value={
                    trade.entry_order_type
                      ? trade.entry_order_type === "market"
                        ? "Market"
                        : "Limit"
                      : PLACEHOLDER
                  }
                />
                <Field label="Risiko" value={fmtUsd(trade.risk_usd)} />
                <Field
                  label="Risiko %"
                  value={
                    trade.risk_pct !== null
                      ? fmtPct(trade.risk_pct / 100)
                      : PLACEHOLDER
                  }
                />
                <Field
                  label="Risk-Modifier"
                  value={fmtNum(trade.risk_modifier, 2)}
                />
              </CardContent>
            </Card>

            <Card className="border-zinc-800 bg-zinc-900/30">
              <CardHeader>
                <CardTitle className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Risk-Rechner-Ergebnis
                </CardTitle>
              </CardHeader>
              <CardContent className="divide-y divide-zinc-800/60">
                <Field
                  label="Richtung"
                  value={
                    trade.direction
                      ? trade.direction === "long"
                        ? "Long"
                        : "Short"
                      : PLACEHOLDER
                  }
                />
                <Field
                  label="Positionsgröße"
                  value={fmtNum(trade.position_size_coins, 5)}
                />
                <Field
                  label="Notional"
                  value={fmtUsd(trade.position_size_notional)}
                />
                <Field
                  label="Leverage"
                  value={
                    trade.leverage !== null
                      ? `${fmtNum(trade.leverage, 1)}×`
                      : PLACEHOLDER
                  }
                />
                <Field
                  label="Erwarteter Verlust"
                  value={fmtUsd(trade.expected_loss)}
                />
                <Field
                  label="Entry-Fee"
                  hint="bei Anlage eingefroren"
                  value={
                    trade.snap_entry_fee_pct !== null
                      ? `${fmtNum(trade.snap_entry_fee_pct * 100, 4)}%`
                      : PLACEHOLDER
                  }
                />
                <Field
                  label="Exit-Fee"
                  hint="bei Anlage eingefroren"
                  value={
                    trade.snap_exit_fee_pct !== null
                      ? `${fmtNum(trade.snap_exit_fee_pct * 100, 4)}%`
                      : PLACEHOLDER
                  }
                />
              </CardContent>
            </Card>

            <Card className="border-zinc-800 bg-zinc-900/30">
              <CardHeader>
                <CardTitle className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Ausführung
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {/* Deviation prominent — Ausführungsqualität */}
                <div className="rounded-md border border-zinc-800 bg-zinc-950 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-zinc-500">
                    Abweichung (Ausführungsqualität)
                  </div>
                  <div className="mt-1 font-mono text-2xl tabular-nums text-zinc-50">
                    {fmtPctValue(trade.deviation_pct)}
                  </div>
                </div>
                <div className="divide-y divide-zinc-800/60">
                  <Field
                    label="Tatsächlicher Entry"
                    value={fmtNum(trade.actual_entry, 4)}
                  />
                  <Field
                    label="Tatsächlicher Stop"
                    value={fmtNum(trade.actual_stop, 4)}
                  />
                  <Field
                    label="Exit-Preis"
                    value={fmtNum(trade.exit_price, 4)}
                  />
                  <Field
                    label="Slippage"
                    value={fmtNum(trade.slippage, 4)}
                  />
                  <Field label="Fees" value={fmtUsd(trade.fees_paid)} />
                  <Field label="Funding" value={fmtUsd(trade.funding_paid)} />
                  <Field
                    label="Realisierter PnL"
                    value={fmtUsd(trade.realized_pnl_usd, { sign: true })}
                    accent={winLossColor(trade.win_loss)}
                  />
                  <Field
                    label="R-Wert"
                    value={fmtR(trade.r_value)}
                    accent={winLossColor(trade.win_loss)}
                  />
                  <Field
                    label="Ergebnis"
                    value={
                      trade.win_loss
                        ? WIN_LOSS_LABEL[trade.win_loss]
                        : PLACEHOLDER
                    }
                    accent={winLossColor(trade.win_loss)}
                  />
                  <Field
                    label="Kontostand danach"
                    value={fmtUsd(trade.balance_after)}
                  />
                  <Field
                    label="Dauer"
                    value={fmtDuration(trade.duration_seconds)}
                  />
                </div>
              </CardContent>
            </Card>
          </section>

          {/* Übergänge */}
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Nächster Schritt
            </h2>
            <TransitionPanel trade={trade} onDone={reload} />
          </section>

          {/* Nachtraegliche Korrektur der Ausfuehrung */}
          {CORRECTABLE_STAGES.includes(trade.stage) ? (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                Ausführung korrigieren
              </h2>
              <CorrectionPanel trade={trade} onDone={reload} />
            </section>
          ) : null}

          {/* Notizen */}
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Notizen
            </h2>
            <NotesEditor trade={trade} onSaved={(t) => setTrade(t)} />
          </section>

          {/* Gefahrenzone */}
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Gefahrenzone
            </h2>
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-red-500/20 bg-red-500/[0.04] p-3">
              <span className="text-sm text-zinc-400">
                Trade löschen — der Kontostand-Beitrag dieses Trades wird
                zurückgerechnet.
              </span>
              <Button
                variant="outline"
                className="ml-auto border-red-500/30 bg-transparent text-red-400/90 hover:bg-red-500/10 hover:text-red-300"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="size-4" />
                Löschen
              </Button>
            </div>
            <ConfirmDialog
              open={deleteOpen}
              onOpenChange={setDeleteOpen}
              title="Live-Trade löschen?"
              description={
                <span className="flex flex-col gap-2">
                  <span>
                    Löscht Trade #{trade.id} unwiderruflich, inklusive
                    Zeitstempeln und Ausführungsdaten.
                  </span>
                  <span className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-300">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    <span>
                      Der Kontostand-Beitrag dieses Trades wird zurückgerechnet
                      — der Saldo ändert sich.
                    </span>
                  </span>
                </span>
              }
              confirmLabel="Endgültig löschen"
              destructive
              onConfirm={async () => {
                await deleteLiveTrade(trade.id);
                router.push("/live");
              }}
            />
          </section>
        </>
      ) : null}
    </div>
  );
}
