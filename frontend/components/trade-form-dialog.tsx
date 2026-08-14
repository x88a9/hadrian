"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, createTrade, updateTrade } from "@/lib/api";
import type {
  Direction,
  Trade,
  TradeCreatePayload,
  TradeUpdatePayload,
  WinLoss,
} from "@/lib/types";

// "leer" = kein Direction/WinLoss gesetzt (Select-Sentinelwert, da base-ui
// Select keinen leeren value erlaubt).
const NONE = "__none__";

// base-ui rendert in <Select.Value> den rohen value, solange dem Root kein
// `items`-Mapping gegeben wird (siehe SelectRoot.Props.items).
const DIRECTION_ITEMS: Record<string, string> = {
  [NONE]: "—",
  long: "Long",
  short: "Short",
};

const WIN_LOSS_ITEMS: Record<string, string> = {
  [NONE]: "—",
  win: "Win",
  loss: "Loss",
  draw: "Draw",
};

interface FormState {
  trade_datetime: string; // datetime-local ("YYYY-MM-DDTHH:mm") oder ""
  zone: string;
  timeframe: string;
  entry: string;
  sl: string;
  exit: string;
  direction: "" | Direction;
  r_value: string;
  win_loss: "" | WinLoss;
}

function num(value: string): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function numEq(a: number | null, b: number | null): boolean {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  return Math.abs(a - b) < 1e-9;
}

// xlsx-Regel: Win wenn R>0, Loss wenn R<-0.1, sonst (inkl. R==0) Draw.
function deriveWinLoss(r: number): WinLoss {
  if (r > 0) return "win";
  if (r < -0.1) return "loss";
  return "draw";
}

function emptyState(defaultTimeframe: string | null | undefined): FormState {
  return {
    trade_datetime: "",
    zone: "",
    timeframe: defaultTimeframe ?? "",
    entry: "",
    sl: "",
    exit: "",
    direction: "",
    r_value: "",
    win_loss: "",
  };
}

function fromTrade(trade: Trade): FormState {
  return {
    trade_datetime: trade.trade_datetime
      ? trade.trade_datetime.slice(0, 16)
      : "",
    zone: trade.zone ?? "",
    timeframe: trade.timeframe ?? "",
    entry: trade.entry !== null ? String(trade.entry) : "",
    sl: trade.sl !== null ? String(trade.sl) : "",
    exit: trade.exit !== null ? String(trade.exit) : "",
    direction: trade.direction ?? "",
    r_value: trade.r_value !== null ? String(trade.r_value) : "",
    win_loss: trade.win_loss ?? "",
  };
}

export interface TradeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  systemId: number;
  // Anlage-Modus: Timeframe des Systems vorbelegen.
  defaultTimeframe?: string | null;
  // Edit-Modus: vorhandener Trade zum Vorbefüllen.
  trade?: Trade;
  // Callback nach erfolgreicher Mutation (Reload).
  onSaved: () => void;
}

const numInputCls = "font-mono tabular-nums";

export function TradeFormDialog({
  open,
  onOpenChange,
  mode,
  systemId,
  defaultTimeframe,
  trade,
  onSaved,
}: TradeFormDialogProps) {
  const [form, setForm] = useState<FormState>(() =>
    emptyState(defaultTimeframe),
  );
  // Sobald der Nutzer R/W-L selbst anfasst, keine Auto-Vorbefüllung mehr.
  const [rTouched, setRTouched] = useState(false);
  const [wlTouched, setWlTouched] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Beim Öffnen (oder Trade-Wechsel) initialisieren.
  useEffect(() => {
    if (!open) return;
    setError(null);
    if (mode === "edit" && trade) {
      setForm(fromTrade(trade));
      // Vorhandene Werte nicht automatisch überschreiben.
      setRTouched(trade.r_value !== null);
      setWlTouched(trade.win_loss !== null);
    } else {
      setForm(emptyState(defaultTimeframe));
      setRTouched(false);
      setWlTouched(false);
    }
  }, [open, mode, trade, defaultTimeframe]);

  // Brutto-R aus Entry/SL/Exit/Direction (nur wenn vollständig).
  const autoR = useMemo<number | null>(() => {
    const e = num(form.entry);
    const s = num(form.sl);
    const x = num(form.exit);
    if (e === null || s === null || x === null || form.direction === "") {
      return null;
    }
    const risk = Math.abs(e - s);
    if (risk === 0) return null;
    const r = form.direction === "long" ? (x - e) / risk : (e - x) / risk;
    return Math.round(r * 1000) / 1000;
  }, [form.entry, form.sl, form.exit, form.direction]);

  // R vorbefüllen, solange der Nutzer es nicht selbst angefasst hat.
  useEffect(() => {
    if (rTouched || autoR === null) return;
    setForm((prev) =>
      prev.r_value === String(autoR) ? prev : { ...prev, r_value: String(autoR) },
    );
  }, [autoR, rTouched]);

  // W/L aus dem aktuellen R ableiten, solange nicht selbst angefasst.
  useEffect(() => {
    if (wlTouched) return;
    const r = num(form.r_value);
    if (r === null) return;
    const wl = deriveWinLoss(r);
    setForm((prev) => (prev.win_loss === wl ? prev : { ...prev, win_loss: wl }));
  }, [form.r_value, wlTouched]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const showBruttoHint = autoR !== null && !rTouched;
  const importedWarning = mode === "edit" && trade && trade.source !== "ui";

  async function handleSubmit() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      if (mode === "create") {
        const payload: TradeCreatePayload = {
          system_id: systemId,
          source: "ui",
          trade_datetime: form.trade_datetime || null,
          zone: form.zone.trim() || null,
          timeframe: form.timeframe.trim() || null,
          entry: num(form.entry),
          sl: num(form.sl),
          exit: num(form.exit),
          direction: form.direction || null,
          r_value: num(form.r_value),
          win_loss: form.win_loss || null,
        };
        await createTrade(payload);
      } else if (trade) {
        // Nur geänderte Felder senden (exclude_unset-Semantik).
        const payload: TradeUpdatePayload = {};
        const origDt = trade.trade_datetime
          ? trade.trade_datetime.slice(0, 16)
          : "";
        if (form.trade_datetime !== origDt) {
          payload.trade_datetime = form.trade_datetime || null;
        }
        if (form.zone.trim() !== (trade.zone ?? "").trim()) {
          payload.zone = form.zone.trim() || null;
        }
        if (form.timeframe.trim() !== (trade.timeframe ?? "").trim()) {
          payload.timeframe = form.timeframe.trim() || null;
        }
        if (!numEq(num(form.entry), trade.entry)) payload.entry = num(form.entry);
        if (!numEq(num(form.sl), trade.sl)) payload.sl = num(form.sl);
        if (!numEq(num(form.exit), trade.exit)) payload.exit = num(form.exit);
        if ((form.direction || null) !== trade.direction) {
          payload.direction = form.direction || null;
        }
        if (!numEq(num(form.r_value), trade.r_value)) {
          payload.r_value = num(form.r_value);
        }
        if ((form.win_loss || null) !== trade.win_loss) {
          payload.win_loss = form.win_loss || null;
        }
        if (Object.keys(payload).length === 0) {
          onOpenChange(false);
          return;
        }
        await updateTrade(trade.id, payload);
      } else {
        return;
      }
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Speichern fehlgeschlagen.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Trade hinzufügen" : "Trade bearbeiten"}
          </DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "Manueller Trade (source=ui) — überlebt jeden Re-Import."
              : "Änderungen wirken sich sofort auf die Kennzahlen aus."}
          </DialogDescription>
        </DialogHeader>

        {importedWarning ? (
          <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            Importierter Trade (source={trade?.source}) — Änderungen werden beim
            nächsten Re-Import überschrieben.
          </p>
        ) : null}

        <div className="flex flex-col gap-4">
          {/* Datum / Zone / Timeframe */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-datetime">Datum / Zeit</Label>
              <Input
                id="tr-datetime"
                type="datetime-local"
                className="[color-scheme:dark]"
                value={form.trade_datetime}
                onChange={(e) => set("trade_datetime", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-zone">Zone</Label>
              <Input
                id="tr-zone"
                value={form.zone}
                onChange={(e) => set("zone", e.target.value)}
                placeholder="optional"
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-tf">Timeframe</Label>
              <Input
                id="tr-tf"
                value={form.timeframe}
                onChange={(e) => set("timeframe", e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>

          {/* Entry / SL / Exit */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-entry">Entry</Label>
              <Input
                id="tr-entry"
                type="number"
                inputMode="decimal"
                className={numInputCls}
                value={form.entry}
                onChange={(e) => set("entry", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-sl">Stop Loss</Label>
              <Input
                id="tr-sl"
                type="number"
                inputMode="decimal"
                className={numInputCls}
                value={form.sl}
                onChange={(e) => set("sl", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-exit">Exit</Label>
              <Input
                id="tr-exit"
                type="number"
                inputMode="decimal"
                className={numInputCls}
                value={form.exit}
                onChange={(e) => set("exit", e.target.value)}
              />
            </div>
          </div>

          {/* Direction / R / W-L */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label>Direction</Label>
              <Select
                items={DIRECTION_ITEMS}
                value={form.direction || NONE}
                onValueChange={(v) =>
                  set("direction", v === NONE ? "" : (v as Direction))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  <SelectItem value="long">Long</SelectItem>
                  <SelectItem value="short">Short</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tr-r">R-Wert</Label>
              <Input
                id="tr-r"
                type="number"
                inputMode="decimal"
                className={numInputCls}
                value={form.r_value}
                onChange={(e) => {
                  setRTouched(true);
                  set("r_value", e.target.value);
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Win / Loss</Label>
              <Select
                items={WIN_LOSS_ITEMS}
                value={form.win_loss || NONE}
                onValueChange={(v) => {
                  setWlTouched(true);
                  set("win_loss", v === NONE ? "" : (v as WinLoss));
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>—</SelectItem>
                  <SelectItem value="win">Win</SelectItem>
                  <SelectItem value="loss">Loss</SelectItem>
                  <SelectItem value="draw">Draw</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {showBruttoHint ? (
            <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              Vorbefüllung = Brutto-R — für Netto nach Kosten anpassen.
            </p>
          ) : null}

          {error ? (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <DialogClose
            render={
              <Button
                variant="outline"
                disabled={pending}
                className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
              />
            }
          >
            Abbrechen
          </DialogClose>
          <Button onClick={() => void handleSubmit()} disabled={pending}>
            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
            {mode === "create" ? "Hinzufügen" : "Speichern"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
