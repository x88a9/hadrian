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
import { ApiError, duplicateStrategy } from "@/lib/api";
import type { StrategyDetail, StrategySummary } from "@/lib/types";

export interface StrategyDuplicateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  strategy: StrategySummary | StrategyDetail | null;
  onDuplicated: (strategy: StrategyDetail) => void;
}

export function StrategyDuplicateDialog({
  open,
  onOpenChange,
  strategy,
  onDuplicated,
}: StrategyDuplicateDialogProps) {
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setName(strategy ? `${strategy.name} (Kopie)` : "");
  }, [open, strategy]);

  const trimmedName = name.trim();
  const canSubmit = !pending && trimmedName.length > 0 && strategy !== null;

  async function handleSubmit() {
    if (!canSubmit || !strategy) return;
    setPending(true);
    setError(null);
    try {
      const duplicated = await duplicateStrategy(strategy.id, {
        name: trimmedName,
      });
      onDuplicated(duplicated);
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Duplizieren fehlgeschlagen.",
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
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Strategie duplizieren</DialogTitle>
          <DialogDescription>
            {strategy
              ? `Erstellt eine unabhaengige Kopie von „${strategy.name}" mit eigener Versionshistorie.`
              : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dup-name">Name der Kopie</Label>
          <Input
            id="dup-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="off"
          />
        </div>

        {error ? (
          <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}

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
            Duplizieren
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
