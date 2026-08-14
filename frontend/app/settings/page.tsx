"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Loader2,
  Pencil,
  Plus,
  RotateCw,
  ServerCrash,
  Wallet,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  correctBalance,
  createAssetSetting,
  createVenue,
  getAssetSettings,
  getBalance,
  getVenues,
  updateVenue,
} from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { fmtUsd } from "@/lib/live-format";
import { cn } from "@/lib/utils";
import type {
  AccountBalanceResponse,
  AssetSetting,
  AssetSettingCreatePayload,
  BalanceChangeType,
  Venue,
} from "@/lib/types";

// --- Einheiten-Konvention (siehe Aufgaben-Brief) --------------------------
// Fees liegen im Backend als BRUCHTEIL vor (0.000144 == 0.0144 %). Die UI
// arbeitet durchgaengig in Prozent: Anzeige = Bruchteil * 100, Eingabe wird
// vor dem POST wieder durch 100 geteilt.
// min_position_size und leverage_buffer sind KEINE Fees -> 1:1.
// deviation_allowed_pct ist ebenfalls als Bruchteil gespeichert (0.05); wir
// zeigen und nehmen sie hier bewusst 1:1 als Bruchteil (0.05), damit der Wert
// exakt dem Backend-Snapshot entspricht und keine Prozent-Doppeldeutung
// entsteht. Das Label weist auf die Bruchteil-Schreibweise hin.

const FEE_DECIMALS = 4;

function feeFractionToPct(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) {
    return "—";
  }
  return `${(fraction * 100).toFixed(FEE_DECIMALS)}%`;
}

function num(value: string): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function apiMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === 0
      ? "Backend nicht erreichbar. Läuft der API-Server?"
      : err.message;
  }
  return err instanceof Error ? err.message : "Unbekannter Fehler.";
}

const CHANGE_TYPE_LABEL: Record<BalanceChangeType, string> = {
  initial: "Initial",
  trade_close: "Trade",
  manual: "Manuell",
};

function changeTypeClass(t: BalanceChangeType): string {
  switch (t) {
    case "initial":
      return "bg-zinc-500/15 text-zinc-300 border-zinc-500/30";
    case "trade_close":
      return "bg-sky-500/15 text-sky-400 border-sky-500/30";
    case "manual":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
  }
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const [venues, setVenues] = useState<Venue[] | null>(null);
  const [balance, setBalance] = useState<AccountBalanceResponse | null>(null);
  const [settingsByVenue, setSettingsByVenue] = useState<
    Record<number, AssetSetting[]>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; offline: boolean } | null>(
    null,
  );

  const [venueDialog, setVenueDialog] = useState<
    { mode: "create" } | { mode: "edit"; venue: Venue } | null
  >(null);
  const [feesVenueId, setFeesVenueId] = useState<number | null>(null);
  const [balanceOpen, setBalanceOpen] = useState(false);

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    try {
      const [venuesRes, balanceRes] = await Promise.all([
        getVenues(),
        getBalance(),
      ]);
      const settingsEntries = await Promise.all(
        venuesRes.items.map(
          async (v) => [v.id, await getAssetSettings(v.id)] as const,
        ),
      );
      setVenues(venuesRes.items);
      setBalance(balanceRes);
      setSettingsByVenue(Object.fromEntries(settingsEntries));
      setError(null);
    } catch (err) {
      const offline = err instanceof ApiError && err.status === 0;
      setError({ message: apiMessage(err), offline });
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  const feesVenue =
    feesVenueId !== null
      ? (venues ?? []).find((v) => v.id === feesVenueId) ?? null
      : null;

  return (
    <div className="flex flex-col gap-8">
      <header>
        <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
          Hadrian³
        </span>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
          Einstellungen
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Venues, Handelskosten (Fees) und Kontostand für das Live-Trading.
        </p>
      </header>

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Einstellungen werden geladen…
        </div>
      ) : null}

      {!loading && error ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/30 px-6 py-20 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950 text-zinc-400">
            {error.offline ? (
              <ServerCrash className="size-6" />
            ) : (
              <AlertTriangle className="size-6" />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-200">
              Einstellungen konnten nicht geladen werden
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              {error.message}
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

      {!loading && !error && venues ? (
        <>
          {/* --- Venues --- */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <SectionTitle>Venues</SectionTitle>
              <Button
                size="sm"
                onClick={() => setVenueDialog({ mode: "create" })}
                className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
              >
                <Plus className="size-4" />
                Venue anlegen
              </Button>
            </div>

            {venues.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-14 text-center">
                <p className="text-sm font-medium text-zinc-300">
                  Noch keine Venues angelegt.
                </p>
                <p className="max-w-md text-sm text-zinc-500">
                  Lege eine Venue an, um Handelskosten zu pflegen und Trades
                  zuzuordnen.
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {venues.map((v) => (
                  <Card
                    key={v.id}
                    className="border-none bg-zinc-900/40 ring-zinc-800"
                  >
                    <CardHeader>
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-zinc-100">
                          {v.name}
                        </CardTitle>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setVenueDialog({ mode: "edit", venue: v })
                          }
                          className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
                        >
                          <Pencil className="size-3.5" />
                          Umbenennen
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2 text-sm">
                      {v.notes ? (
                        <p className="whitespace-pre-wrap text-zinc-400">
                          {v.notes}
                        </p>
                      ) : (
                        <p className="text-zinc-600">Keine Notizen.</p>
                      )}
                      <div className="text-xs text-zinc-500">
                        {v.current_settings ? (
                          <span className="font-mono tabular-nums">
                            {v.current_settings.asset} · Entry{" "}
                            {feeFractionToPct(v.current_settings.entry_fee_pct)}{" "}
                            · Exit{" "}
                            {feeFractionToPct(v.current_settings.exit_fee_pct)}{" "}
                            · Min {v.current_settings.min_position_size}
                          </span>
                        ) : (
                          <span className="text-amber-400/80">
                            Keine Fees hinterlegt.
                          </span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>

          {/* --- Asset-Settings (Fees) --- */}
          {venues.length > 0 ? (
            <section>
              <SectionTitle>Asset-Settings (Fees)</SectionTitle>
              <div className="flex flex-col gap-4">
                {venues.map((v) => {
                  const history = settingsByVenue[v.id] ?? [];
                  const currentId = v.current_settings?.id ?? history[0]?.id;
                  return (
                    <Card
                      key={v.id}
                      className="border-none bg-zinc-900/40 ring-zinc-800"
                    >
                      <CardHeader>
                        <div className="flex items-center justify-between gap-2">
                          <CardTitle className="text-zinc-100">
                            {v.name}
                          </CardTitle>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setFeesVenueId(v.id)}
                            className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
                          >
                            <Plus className="size-3.5" />
                            Fees ändern
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent className="flex flex-col gap-3">
                        <p className="text-xs text-zinc-500">
                          „Fees ändern" legt eine{" "}
                          <span className="text-zinc-300">neue Version</span> an
                          — bestehende Trades behalten ihren Snapshot.
                        </p>
                        {history.length === 0 ? (
                          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
                            Noch keine Fees hinterlegt — lege die erste Version
                            an.
                          </p>
                        ) : (
                          <div className="overflow-hidden rounded-lg border border-zinc-800">
                            <Table>
                              <TableHeader>
                                <TableRow className="border-zinc-800 hover:bg-transparent">
                                  <TableHead className="text-zinc-400">
                                    Gültig ab
                                  </TableHead>
                                  <TableHead className="text-zinc-400">
                                    Asset
                                  </TableHead>
                                  <TableHead className="text-right text-zinc-400">
                                    Entry-Fee
                                  </TableHead>
                                  <TableHead className="text-right text-zinc-400">
                                    Exit-Fee
                                  </TableHead>
                                  <TableHead className="text-right text-zinc-400">
                                    Min-Größe
                                  </TableHead>
                                  <TableHead className="text-right text-zinc-400">
                                    Lev-Buffer
                                  </TableHead>
                                  <TableHead className="text-right text-zinc-400">
                                    Dev ↑ / ↓
                                  </TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {history.map((s) => {
                                  const isCurrent = s.id === currentId;
                                  return (
                                    <TableRow
                                      key={s.id}
                                      className="border-zinc-800 hover:bg-zinc-900/60"
                                    >
                                      <TableCell className="font-mono text-xs tabular-nums text-zinc-300">
                                        <span className="inline-flex items-center gap-2">
                                          {fmtDateTime(s.valid_from)}
                                          {isCurrent ? (
                                            <span className="rounded border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-400">
                                              aktuell
                                            </span>
                                          ) : null}
                                        </span>
                                      </TableCell>
                                      <TableCell className="text-zinc-300">
                                        {s.asset}
                                      </TableCell>
                                      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                                        {feeFractionToPct(s.entry_fee_pct)}
                                      </TableCell>
                                      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                                        {feeFractionToPct(s.exit_fee_pct)}
                                      </TableCell>
                                      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                                        {s.min_position_size}
                                      </TableCell>
                                      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                                        {s.leverage_buffer}
                                      </TableCell>
                                      <TableCell className="text-right font-mono tabular-nums text-zinc-400">
                                        {s.upside_deviation_allowed_pct} /{" "}
                                        {s.downside_deviation_allowed_pct}
                                      </TableCell>
                                    </TableRow>
                                  );
                                })}
                              </TableBody>
                            </Table>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </section>
          ) : null}

          {/* --- Kontostand --- */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <SectionTitle>Kontostand</SectionTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setBalanceOpen(true)}
                className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              >
                <Wallet className="size-3.5" />
                Korrigieren
              </Button>
            </div>

            <Card className="border-none bg-zinc-900/40 ring-zinc-800">
              <CardContent className="flex flex-col gap-4 pt-1">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-zinc-500">
                    Aktueller Stand
                  </div>
                  <div className="font-mono text-4xl tabular-nums text-zinc-50">
                    {fmtUsd(balance?.current_balance ?? null)}
                  </div>
                </div>

                {balance && balance.history.length > 0 ? (
                  <div className="overflow-hidden rounded-lg border border-zinc-800">
                    <Table>
                      <TableHeader>
                        <TableRow className="border-zinc-800 hover:bg-transparent">
                          <TableHead className="text-zinc-400">
                            Zeitpunkt
                          </TableHead>
                          <TableHead className="text-zinc-400">Typ</TableHead>
                          <TableHead className="text-right text-zinc-400">
                            Delta
                          </TableHead>
                          <TableHead className="text-right text-zinc-400">
                            Stand
                          </TableHead>
                          <TableHead className="text-zinc-400">Notiz</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {balance.history.map((e) => (
                          <TableRow
                            key={e.id}
                            className="border-zinc-800 hover:bg-zinc-900/60"
                          >
                            <TableCell className="font-mono text-xs tabular-nums text-zinc-400">
                              {fmtDateTime(e.as_of)}
                            </TableCell>
                            <TableCell>
                              <span
                                className={cn(
                                  "rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                                  changeTypeClass(e.change_type),
                                )}
                              >
                                {CHANGE_TYPE_LABEL[e.change_type]}
                              </span>
                            </TableCell>
                            <TableCell
                              className={cn(
                                "text-right font-mono tabular-nums",
                                e.delta === null || e.delta === 0
                                  ? "text-zinc-500"
                                  : e.delta > 0
                                    ? "text-emerald-400"
                                    : "text-red-400",
                              )}
                            >
                              {e.delta === null
                                ? "—"
                                : fmtUsd(e.delta, { sign: true })}
                            </TableCell>
                            <TableCell className="text-right font-mono tabular-nums text-zinc-200">
                              {fmtUsd(e.balance)}
                            </TableCell>
                            <TableCell className="max-w-xs truncate text-zinc-400">
                              {e.note ?? "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="rounded-md border border-zinc-800 bg-zinc-900/30 px-3 py-2 text-sm text-zinc-500">
                    Noch keine Kontostand-Historie.
                  </p>
                )}
              </CardContent>
            </Card>
          </section>
        </>
      ) : null}

      {/* --- Dialoge --- */}
      <VenueDialog
        key={
          venueDialog
            ? venueDialog.mode === "edit"
              ? `edit-${venueDialog.venue.id}`
              : "create"
            : "closed"
        }
        state={venueDialog}
        onClose={() => setVenueDialog(null)}
        onSaved={() => void load(false)}
      />

      <FeesDialog
        key={feesVenue ? `fees-${feesVenue.id}` : "fees-closed"}
        venue={feesVenue}
        onClose={() => setFeesVenueId(null)}
        onSaved={() => void load(false)}
      />

      <BalanceDialog
        key={balanceOpen ? "balance-open" : "balance-closed"}
        open={balanceOpen}
        currentBalance={balance?.current_balance ?? 0}
        onClose={() => setBalanceOpen(false)}
        onSaved={() => void load(false)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Venue anlegen / umbenennen
// ---------------------------------------------------------------------------

function VenueDialog({
  state,
  onClose,
  onSaved,
}: {
  state: { mode: "create" } | { mode: "edit"; venue: Venue } | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const editing = state?.mode === "edit" ? state.venue : null;
  const [name, setName] = useState(editing?.name ?? "");
  const [notes, setNotes] = useState(editing?.notes ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (pending) return;
    if (name.trim() === "") {
      setError("Name darf nicht leer sein.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const noteVal = notes.trim() || null;
      if (state?.mode === "edit") {
        await updateVenue(state.venue.id, name.trim(), noteVal);
      } else {
        await createVenue(name.trim(), noteVal);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={state !== null}
      onOpenChange={(next) => {
        if (pending) return;
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editing ? "Venue umbenennen" : "Venue anlegen"}
          </DialogTitle>
          <DialogDescription>
            {editing
              ? "Name und Notizen der Venue anpassen."
              : "Neue Handelsvenue für Live-Trades anlegen."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="venue-name">Name</Label>
            <Input
              id="venue-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Hyperliquid"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="venue-notes">Notizen</Label>
            <Textarea
              id="venue-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="optional"
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
          <Button onClick={() => void handleSubmit()} disabled={pending}>
            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
            {editing ? "Speichern" : "Anlegen"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Fees ändern (neue Asset-Settings-Version)
// ---------------------------------------------------------------------------

function FeesDialog({
  venue,
  onClose,
  onSaved,
}: {
  venue: Venue | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const cur = venue?.current_settings ?? null;
  // Fees als Prozent vorbelegen (Bruchteil * 100); Rest 1:1.
  const [asset, setAsset] = useState(cur?.asset ?? "DEFAULT");
  const [entryFee, setEntryFee] = useState(
    cur ? String(cur.entry_fee_pct * 100) : "",
  );
  const [exitFee, setExitFee] = useState(
    cur ? String(cur.exit_fee_pct * 100) : "",
  );
  const [minSize, setMinSize] = useState(
    cur ? String(cur.min_position_size) : "",
  );
  const [levBuffer, setLevBuffer] = useState(
    cur ? String(cur.leverage_buffer) : "",
  );
  const [upDev, setUpDev] = useState(
    cur ? String(cur.upside_deviation_allowed_pct) : "",
  );
  const [downDev, setDownDev] = useState(
    cur ? String(cur.downside_deviation_allowed_pct) : "",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (pending || !venue) return;
    const entry = num(entryFee);
    const exit = num(exitFee);
    const min = num(minSize);
    if (entry === null || exit === null || min === null) {
      setError("Entry-Fee, Exit-Fee und Min-Größe sind Pflichtfelder.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      // Prozent-Eingabe vor dem POST wieder in Bruchteil umrechnen.
      const payload: AssetSettingCreatePayload = {
        asset: asset.trim() || "DEFAULT",
        entry_fee_pct: entry / 100,
        exit_fee_pct: exit / 100,
        min_position_size: min,
      };
      const lev = num(levBuffer);
      if (lev !== null) payload.leverage_buffer = lev;
      const up = num(upDev);
      if (up !== null) payload.upside_deviation_allowed_pct = up;
      const down = num(downDev);
      if (down !== null) payload.downside_deviation_allowed_pct = down;

      await createAssetSetting(venue.id, payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setPending(false);
    }
  }

  const numCls = "font-mono tabular-nums";

  return (
    <Dialog
      open={venue !== null}
      onOpenChange={(next) => {
        if (pending) return;
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            Fees ändern{venue ? ` — ${venue.name}` : ""}
          </DialogTitle>
          <DialogDescription>
            Legt eine <span className="text-zinc-300">neue Version</span> an —
            bestehende Trades behalten ihren Snapshot.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fee-asset">Asset</Label>
            <Input
              id="fee-asset"
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-entry">Entry-Fee (%)</Label>
              <Input
                id="fee-entry"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={entryFee}
                onChange={(e) => setEntryFee(e.target.value)}
                placeholder="z. B. 0.0144"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-exit">Exit-Fee (%)</Label>
              <Input
                id="fee-exit"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={exitFee}
                onChange={(e) => setExitFee(e.target.value)}
                placeholder="z. B. 0.0144"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-min">Min-Positionsgröße</Label>
              <Input
                id="fee-min"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={minSize}
                onChange={(e) => setMinSize(e.target.value)}
                placeholder="z. B. 0.001"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-lev">Leverage-Buffer</Label>
              <Input
                id="fee-lev"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={levBuffer}
                onChange={(e) => setLevBuffer(e.target.value)}
                placeholder="optional"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-up">Deviation ↑ (Bruchteil)</Label>
              <Input
                id="fee-up"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={upDev}
                onChange={(e) => setUpDev(e.target.value)}
                placeholder="z. B. 0.05"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fee-down">Deviation ↓ (Bruchteil)</Label>
              <Input
                id="fee-down"
                type="number"
                inputMode="decimal"
                className={numCls}
                value={downDev}
                onChange={(e) => setDownDev(e.target.value)}
                placeholder="z. B. 0.05"
              />
            </div>
          </div>

          <p className="text-xs text-zinc-500">
            Fees als Prozent eingeben (0.0144 = 0,0144 %). Deviation als
            Bruchteil (0.05 = 5 %) — wird unverändert gespeichert.
          </p>

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
            Neue Version anlegen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Kontostand korrigieren
// ---------------------------------------------------------------------------

function BalanceDialog({
  open,
  currentBalance,
  onClose,
  onSaved,
}: {
  open: boolean;
  currentBalance: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [balance, setBalance] = useState(String(currentBalance));
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (pending) return;
    const value = num(balance);
    if (value === null) {
      setError("Bitte einen gültigen Kontostand eingeben.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await correctBalance(value, note.trim() || null);
      onSaved();
      onClose();
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Kontostand korrigieren</DialogTitle>
          <DialogDescription>
            Setzt den <span className="text-zinc-300">absoluten</span> neuen
            Stand (append-only Historie).
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bal-value">Neuer Stand (USD)</Label>
            <Input
              id="bal-value"
              type="number"
              inputMode="decimal"
              className="font-mono tabular-nums"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bal-note">Notiz</Label>
            <Textarea
              id="bal-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="optional (z. B. Einzahlung, Abhebung)"
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
          <Button onClick={() => void handleSubmit()} disabled={pending}>
            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
            Korrigieren
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
