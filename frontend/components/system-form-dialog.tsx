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
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createSystem, updateSystem } from "@/lib/api";
import type {
  SystemDetail,
  SystemStatus,
  SystemUpdatePayload,
} from "@/lib/types";

// Namenskonvention PREFIX-TIMEFRAME-NUMMER[.variante] (Hinweis, keine Sperre).
const NAME_PATTERN =
  /^(B|BB|MR|REV|VP|TREND|FBP|EMA)-[A-Z0-9]+-\d{3}(\.[A-Za-z0-9]+)?$/;

const STATUS_OPTIONS: { value: SystemStatus; label: string }[] = [
  { value: "backtest", label: "Backtest" },
  { value: "live_testing", label: "Live Testing" },
  { value: "active", label: "Active" },
  { value: "retired", label: "Retired" },
];

// base-ui rendert in <Select.Value> den rohen value, solange dem Root kein
// `items`-Mapping gegeben wird (siehe SelectRoot.Props.items).
const STATUS_ITEMS: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((o) => [o.value, o.label]),
);

// Prefix/Timeframe wie das Backend (split_name) aus dem Namen ableiten.
function derivePrefixTimeframe(name: string): {
  prefix: string | null;
  timeframe: string | null;
} {
  if (!name.includes("-")) return { prefix: null, timeframe: null };
  const segments = name.split("-");
  const prefix = segments[0].trim() || null;
  const timeframe =
    segments.length >= 2 && segments[1].trim() ? segments[1].trim() : null;
  return { prefix, timeframe };
}

interface FormState {
  name: string;
  status: SystemStatus;
  asset: string;
  entry_rule: string;
  sl_rule: string;
  tp_rule: string;
  notes: string;
}

function emptyState(): FormState {
  return {
    name: "",
    status: "backtest",
    asset: "",
    entry_rule: "",
    sl_rule: "",
    tp_rule: "",
    notes: "",
  };
}

function fromSystem(system: SystemDetail): FormState {
  return {
    name: system.name,
    status: system.status,
    asset: system.asset ?? "",
    entry_rule: system.entry_rule ?? "",
    sl_rule: system.sl_rule ?? "",
    tp_rule: system.tp_rule ?? "",
    notes: system.notes ?? "",
  };
}

export interface SystemFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  // Edit-Modus: vorhandenes System zum Vorbefüllen.
  system?: SystemDetail;
  // Anlage-Modus: bestehende Namen für die harte Kollisionssperre.
  existingNames?: string[];
  // Callback nach erfolgreichem Speichern (Reload).
  onSaved: (system: SystemDetail) => void;
}

export function SystemFormDialog({
  open,
  onOpenChange,
  mode,
  system,
  existingNames = [],
  onSaved,
}: SystemFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyState);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Beim Öffnen (oder Systemwechsel) Formular initialisieren.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(mode === "edit" && system ? fromSystem(system) : emptyState());
  }, [open, mode, system]);

  const derived = useMemo(
    () => derivePrefixTimeframe(form.name.trim()),
    [form.name],
  );

  const trimmedName = form.name.trim();
  const nameHint =
    mode === "create" && trimmedName.length > 0 && !NAME_PATTERN.test(trimmedName);

  // Harte Sperre nur im Anlage-Modus (POST ist stiller Upsert per Name).
  const existingSet = useMemo(
    () => new Set(existingNames.map((n) => n.toLowerCase())),
    [existingNames],
  );
  const nameCollision =
    mode === "create" &&
    trimmedName.length > 0 &&
    existingSet.has(trimmedName.toLowerCase());

  const canSubmit =
    !pending &&
    (mode === "edit" || (trimmedName.length > 0 && !nameCollision));

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      let saved: SystemDetail;
      if (mode === "create") {
        saved = await createSystem({
          name: trimmedName,
          status: form.status,
          asset: form.asset.trim().toUpperCase() || null,
          entry_rule: form.entry_rule.trim() || null,
          sl_rule: form.sl_rule.trim() || null,
          tp_rule: form.tp_rule.trim() || null,
          notes: form.notes.trim() || null,
        });
      } else if (system) {
        // Nur geänderte Felder senden (exclude_unset-Semantik) — sonst landen
        // ungeänderte Felder unnötig in user_overrides.
        const payload: SystemUpdatePayload = {};
        if (form.status !== system.status) payload.status = form.status;
        const cmp: [keyof SystemUpdatePayload, string, string | null][] = [
          ["asset", form.asset.toUpperCase(), system.asset],
          ["entry_rule", form.entry_rule, system.entry_rule],
          ["sl_rule", form.sl_rule, system.sl_rule],
          ["tp_rule", form.tp_rule, system.tp_rule],
          ["notes", form.notes, system.notes],
        ];
        for (const [key, next, orig] of cmp) {
          const nextVal = next.trim();
          const origVal = (orig ?? "").trim();
          if (nextVal !== origVal) {
            (payload[key] as string | null) = nextVal || null;
          }
        }
        if (Object.keys(payload).length === 0) {
          // Kein Feld geändert -> ohne Request schließen.
          onOpenChange(false);
          return;
        }
        saved = await updateSystem(system.id, payload);
      } else {
        return;
      }
      onSaved(saved);
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
            {mode === "create" ? "Neues System" : "System bearbeiten"}
          </DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "Legt ein UI-System an — vor Re-Import geschützt."
              : `${system?.name ?? ""} — Änderungen werden als user_overrides geschützt.`}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sys-name">Name</Label>
            {mode === "create" ? (
              <Input
                id="sys-name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="z. B. B-15m-001"
                autoComplete="off"
                aria-invalid={nameCollision || undefined}
              />
            ) : (
              <div className="flex h-9 items-center rounded-md border border-zinc-800 bg-zinc-900/40 px-3 text-sm text-zinc-400">
                {form.name}
                <span className="ml-2 text-xs text-zinc-600">
                  (nicht änderbar)
                </span>
              </div>
            )}

            {/* Prefix/Timeframe-Vorschau */}
            {trimmedName.length > 0 ? (
              <p className="text-xs text-zinc-500">
                Prefix{" "}
                <span className="font-mono text-zinc-400">
                  {derived.prefix ?? "—"}
                </span>{" "}
                · Timeframe{" "}
                <span className="font-mono text-zinc-400">
                  {derived.timeframe ?? "—"}
                </span>
              </p>
            ) : null}

            {nameCollision ? (
              <p className="flex items-center gap-1.5 text-xs text-red-400">
                <AlertTriangle className="size-3.5 shrink-0" />
                Name bereits vergeben — würde ein bestehendes System
                überschreiben.
              </p>
            ) : nameHint ? (
              <p className="flex items-center gap-1.5 text-xs text-amber-400">
                <AlertTriangle className="size-3.5 shrink-0" />
                Entspricht nicht der Konvention PREFIX-TIMEFRAME-NUMMER.
              </p>
            ) : null}
          </div>

          {/* Status + Provenance */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Status</Label>
              <Select
                items={STATUS_ITEMS}
                value={form.status}
                onValueChange={(v) => set("status", v as SystemStatus)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {mode === "create" ? (
              <div className="flex flex-col gap-1.5">
                <Label>Herkunft</Label>
                <div className="flex h-9 items-center rounded-md border border-zinc-800 bg-zinc-900/40 px-3 text-sm text-zinc-400">
                  Manuell
                </div>
                <p className="text-xs text-zinc-600">
                  UI-Anlagen sind stets manuell.
                </p>
              </div>
            ) : null}
          </div>

          {/* Asset — bindet die handelbare Schrittweite beim Live-Trade. */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sys-asset">Asset</Label>
            <Input
              id="sys-asset"
              value={form.asset}
              onChange={(e) => set("asset", e.target.value.toUpperCase())}
              placeholder="z. B. BTC, DOT, XMR"
              autoComplete="off"
              className="font-mono uppercase"
            />
            <p className="text-xs text-zinc-500">
              Backtestet auf genau einem Asset. Legt beim Live-Trade die
              handelbare Schrittweite (Lot-Size) fest. Leer = frei wählbar.
            </p>
          </div>

          {/* Regeln */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sys-entry">Entry-Regel</Label>
            <Textarea
              id="sys-entry"
              value={form.entry_rule}
              onChange={(e) => set("entry_rule", e.target.value)}
              placeholder="Einstiegslogik…"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sys-sl">Stop-Loss-Regel</Label>
              <Textarea
                id="sys-sl"
                value={form.sl_rule}
                onChange={(e) => set("sl_rule", e.target.value)}
                placeholder="Stop-Logik…"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sys-tp">Take-Profit-Regel</Label>
              <Textarea
                id="sys-tp"
                value={form.tp_rule}
                onChange={(e) => set("tp_rule", e.target.value)}
                placeholder="Ziel-Logik…"
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sys-notes">Notizen</Label>
            <Textarea
              id="sys-notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Freitext…"
            />
          </div>

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
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
            {mode === "create" ? "Anlegen" : "Speichern"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
