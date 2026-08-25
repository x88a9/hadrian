"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

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
import { ApiError, createStrategy } from "@/lib/api";
import {
  defaultDeclarativeDefinition,
  defaultPythonDefinition,
} from "@/lib/strategy-defaults";
import type { StrategyDetail } from "@/lib/types";

type Direction = "long" | "short" | "both";
type Rules = "declarative" | "python";

const DIRECTION_ITEMS: Record<Direction, string> = {
  long: "Long",
  short: "Short",
  both: "Long & Short",
};

const RULES_ITEMS: Record<Rules, string> = {
  declarative: "Deklarativ (Regel-Baum)",
  python: "Python",
};

interface FormState {
  name: string;
  description: string;
  asset: string;
  timeframe: string;
  direction: Direction;
  rules: Rules;
}

function emptyState(): FormState {
  return {
    name: "",
    description: "",
    asset: "",
    timeframe: "1h",
    direction: "long",
    rules: "declarative",
  };
}

export interface StrategyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (strategy: StrategyDetail) => void;
}

// Legt eine neue Strategie an — die Regel-Details werden im Designer
// (Editor-Tab) bearbeitet, hier wird nur ein gueltiges Startgeruest erzeugt.
export function StrategyFormDialog({
  open,
  onOpenChange,
  onCreated,
}: StrategyFormDialogProps) {
  const [form, setForm] = useState<FormState>(emptyState);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(emptyState());
  }, [open]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const trimmedName = form.name.trim();
  const trimmedAsset = form.asset.trim().toUpperCase();
  const trimmedTimeframe = form.timeframe.trim();
  const canSubmit =
    !pending &&
    trimmedName.length > 0 &&
    trimmedAsset.length > 0 &&
    trimmedTimeframe.length > 0;

  async function handleSubmit() {
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const opts = {
        name: trimmedName,
        description: form.description.trim() || null,
        asset: trimmedAsset,
        timeframe: trimmedTimeframe,
        direction: form.direction,
      };
      const definition =
        form.rules === "python"
          ? defaultPythonDefinition(opts)
          : defaultDeclarativeDefinition(opts);
      const created = await createStrategy({
        name: trimmedName,
        description: opts.description,
        definition,
      });
      onCreated(created);
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Anlegen fehlgeschlagen.",
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
          <DialogTitle>Neue Strategie</DialogTitle>
          <DialogDescription>
            Legt ein gueltiges Startgeruest an. Regeln, Indikatoren und Risk
            werden im Designer bearbeitet.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="strat-name">Name</Label>
            <Input
              id="strat-name"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="z. B. SMA Crossover BTC 1h"
              autoComplete="off"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="strat-desc">Beschreibung</Label>
            <Textarea
              id="strat-desc"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Optional…"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="strat-asset">Asset</Label>
              <Input
                id="strat-asset"
                value={form.asset}
                onChange={(e) => set("asset", e.target.value.toUpperCase())}
                placeholder="z. B. BTC"
                autoComplete="off"
                className="font-mono uppercase"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="strat-tf">Timeframe</Label>
              <Input
                id="strat-tf"
                value={form.timeframe}
                onChange={(e) => set("timeframe", e.target.value)}
                placeholder="z. B. 1h"
                autoComplete="off"
                className="font-mono"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Richtung</Label>
              <Select
                items={DIRECTION_ITEMS}
                value={form.direction}
                onValueChange={(v) => set("direction", v as Direction)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(DIRECTION_ITEMS) as Direction[]).map((d) => (
                    <SelectItem key={d} value={d}>
                      {DIRECTION_ITEMS[d]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Regel-Typ</Label>
              <Select
                items={RULES_ITEMS}
                value={form.rules}
                onValueChange={(v) => set("rules", v as Rules)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(RULES_ITEMS) as Rules[]).map((r) => (
                    <SelectItem key={r} value={r}>
                      {RULES_ITEMS[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
            Anlegen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
