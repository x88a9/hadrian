"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ApiError,
  calcRisk,
  getAssetSettings,
  getBalance,
  getVenues,
} from "@/lib/api";
import { fmtNum, fmtPct } from "@/lib/format";
import { fmtUsd } from "@/lib/live-format";
import { cn } from "@/lib/utils";
import type { RiskCalcRequest, RiskCalcResponse, Venue } from "@/lib/types";

function num(value: string): number | null {
  const t = value.trim();
  if (t === "") return null;
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

// Lot-Size lesbar machen (0.00001 -> "0.00001", 1 -> "1").
function fmtLot(lot: number | null | undefined): string {
  if (lot === null || lot === undefined || !Number.isFinite(lot)) return "—";
  if (lot >= 1) return String(lot);
  const decimals = Math.min(10, Math.max(0, Math.ceil(-Math.log10(lot))));
  return lot.toFixed(decimals);
}

export interface RiskFormValues {
  entry: string;
  stop: string;
  riskMode: "usd" | "pct";
  risk: string;
  modifier: string;
  venueId: number | null;
  asset: string;
  // Optionaler Szenario-Kontostand. Leer = aktueller Kontostand aus den
  // Settings (POST /risk/calc ohne portfolio_size). Aendert die Settings nie.
  portfolio: string;
}

export function defaultRiskForm(
  overrides: Partial<RiskFormValues> = {},
): RiskFormValues {
  return {
    entry: "",
    stop: "",
    riskMode: "usd",
    risk: "",
    modifier: "1",
    venueId: null,
    asset: "",
    portfolio: "",
    ...overrides,
  };
}

export function buildRiskRequest(f: RiskFormValues): RiskCalcRequest | null {
  const entry = num(f.entry);
  const stop = num(f.stop);
  const risk = num(f.risk);
  if (entry === null || stop === null || risk === null || risk <= 0) return null;
  const modifier = num(f.modifier) ?? 1;
  const req: RiskCalcRequest = {
    entry_price: entry,
    stop_price: stop,
    risk_modifier: modifier,
  };
  if (f.riskMode === "usd") req.desired_risk_usd = risk;
  else req.risk_pct = risk;
  if (f.venueId !== null) req.venue_id = f.venueId;
  if (f.asset.trim()) req.asset = f.asset.trim();
  // Nur ein positiver Wert ueberschreibt den Kontostand; leer = Settings.
  const portfolio = num(f.portfolio);
  if (portfolio !== null && portfolio > 0) req.portfolio_size = portfolio;
  return req;
}

const numCls = "font-mono tabular-nums";
const ASSET_AUTO = "__auto__";
const VENUE_DEFAULT = "__default__";

// base-ui rendert in <Select.Value> den rohen value, solange dem Root kein
// `items`-Mapping gegeben wird. Darum bekommt JEDER Select hier sein
// value->Label-Mapping (siehe SelectRoot.Props.items).
const RISK_MODE_ITEMS: Record<string, string> = {
  usd: "USD",
  pct: "% vom Portfolio",
};

function Row({
  label,
  value,
  hint,
  strong,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-sm text-zinc-400">
        {label}
        {hint ? (
          <span className="ml-1 text-xs text-zinc-600">{hint}</span>
        ) : null}
      </span>
      <span
        className={cn(
          "font-mono text-sm tabular-nums",
          strong ? "text-zinc-50" : "text-zinc-100",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Warn({
  tone,
  icon,
  children,
}: {
  tone: "red" | "amber";
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
        tone === "red"
          ? "border-red-500/40 bg-red-500/10 text-red-300"
          : "border-amber-500/40 bg-amber-500/10 text-amber-300",
      )}
    >
      <span className="mt-0.5 shrink-0">
        {icon ?? <AlertTriangle className="size-4" />}
      </span>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export interface RiskCalculatorProps {
  form: RiskFormValues;
  onFormChange: (form: RiskFormValues) => void;
  actionLabel?: string;
  onAction?: (form: RiskFormValues, result: RiskCalcResponse) => void;
  actionPending?: boolean;
  // Asset ist durch das gewählte System vorgegeben (Anzeige statt Auswahl).
  assetLockedTo?: string | null;
  // Erlaubt „Was wäre bei Kontostand X?" (portfolio_size). Reine Vorschau —
  // deshalb nur dort einblenden, wo kein Trade entsteht (siehe /risk).
  allowPortfolioOverride?: boolean;
}

export function RiskCalculator({
  form,
  onFormChange,
  actionLabel,
  onAction,
  actionPending,
  assetLockedTo,
  allowPortfolioOverride = false,
}: RiskCalculatorProps) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [realBalance, setRealBalance] = useState<number | null>(null);
  const [assets, setAssets] = useState<string[]>([]);
  const [result, setResult] = useState<RiskCalcResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVenues()
      .then((r) => setVenues(r.items))
      .catch(() => setVenues([]));
  }, []);

  // Echter Saldo nur als Vergleichswert fuer die Szenario-Anzeige.
  useEffect(() => {
    if (!allowPortfolioOverride) return;
    getBalance()
      .then((b) => setRealBalance(b.current_balance))
      .catch(() => setRealBalance(null));
  }, [allowPortfolioOverride]);

  // Verfügbare Assets der gewählten Venue (für die Auswahl + Schrittweite).
  useEffect(() => {
    getAssetSettings(form.venueId ?? undefined)
      .then((rows) => {
        const seen = new Set<string>();
        const names: string[] = [];
        for (const r of rows) {
          if (!seen.has(r.asset)) {
            seen.add(r.asset);
            names.push(r.asset);
          }
        }
        names.sort((a, b) =>
          a === "DEFAULT" ? 1 : b === "DEFAULT" ? -1 : a.localeCompare(b),
        );
        setAssets(names);
      })
      .catch(() => setAssets([]));
  }, [form.venueId]);

  const venueItems = useMemo(() => {
    const map: Record<string, string> = { [VENUE_DEFAULT]: "Standard" };
    for (const v of venues) map[String(v.id)] = v.name;
    return map;
  }, [venues]);

  const assetItems = useMemo(() => {
    const map: Record<string, string> = { [ASSET_AUTO]: "Standard" };
    for (const a of assets) map[a] = a;
    return map;
  }, [assets]);

  const req = useMemo(() => buildRiskRequest(form), [form]);
  const reqKey = req ? JSON.stringify(req) : "";

  useEffect(() => {
    if (!req) {
      setResult(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      setPending(true);
      calcRisk(req)
        .then((r) => {
          if (!cancelled) {
            setResult(r);
            setError(null);
          }
        })
        .catch((err) => {
          if (cancelled) return;
          setResult(null);
          setError(
            err instanceof ApiError
              ? err.status === 0
                ? "Backend nicht erreichbar."
                : err.message
              : "Berechnung fehlgeschlagen.",
          );
        })
        .finally(() => {
          if (!cancelled) setPending(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqKey]);

  function set<K extends keyof RiskFormValues>(key: K, value: RiskFormValues[K]) {
    onFormChange({ ...form, [key]: value });
  }

  const blocking =
    result && (result.rounds_to_zero || !result.valid_risk || result.leverage_exceeds_max);

  // Szenario aktiv = ein Kontostand ist gesetzt und weicht vom echten ab.
  const portfolioOverride = num(form.portfolio);
  const scenarioActive =
    allowPortfolioOverride &&
    portfolioOverride !== null &&
    portfolioOverride > 0 &&
    (realBalance === null || Math.abs(portfolioOverride - realBalance) > 0.005);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Eingaben */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-950 p-5">
        <h3 className="text-sm font-semibold text-zinc-200">Eingaben</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-entry">Entry</Label>
            <Input
              id="rc-entry"
              type="number"
              inputMode="decimal"
              className={numCls}
              value={form.entry}
              onChange={(e) => set("entry", e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-stop">Stop Loss</Label>
            <Input
              id="rc-stop"
              type="number"
              inputMode="decimal"
              className={numCls}
              value={form.stop}
              onChange={(e) => set("stop", e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label>Risiko-Modus</Label>
            <Select
              items={RISK_MODE_ITEMS}
              value={form.riskMode}
              onValueChange={(v) => set("riskMode", v as "usd" | "pct")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="usd">USD</SelectItem>
                <SelectItem value="pct">% vom Portfolio</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-risk">
              {form.riskMode === "usd" ? "Risiko ($)" : "Risiko (%)"}
            </Label>
            <Input
              id="rc-risk"
              type="number"
              inputMode="decimal"
              className={numCls}
              value={form.risk}
              onChange={(e) => set("risk", e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-mod">Risk-Modifier</Label>
            <Input
              id="rc-mod"
              type="number"
              inputMode="decimal"
              className={numCls}
              value={form.modifier}
              onChange={(e) => set("modifier", e.target.value)}
              placeholder="1.0"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Venue</Label>
            <Select
              items={venueItems}
              value={form.venueId !== null ? String(form.venueId) : VENUE_DEFAULT}
              onValueChange={(v) =>
                set("venueId", v === VENUE_DEFAULT ? null : Number(v))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={VENUE_DEFAULT}>Standard</SelectItem>
                {venues.map((v) => (
                  <SelectItem key={v.id} value={String(v.id)}>
                    {v.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Asset bestimmt die Schrittweite -> immer sichtbar */}
        <div className="flex flex-col gap-1.5">
          <Label>Asset</Label>
          {assetLockedTo ? (
            <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2">
              <span className="font-mono text-sm text-zinc-100">
                {assetLockedTo}
              </span>
              <span className="text-xs text-zinc-500">vom System vorgegeben</span>
            </div>
          ) : (
            <Select
              items={assetItems}
              value={form.asset.trim() === "" ? ASSET_AUTO : form.asset}
              onValueChange={(v) =>
                set("asset", v === ASSET_AUTO || v === null ? "" : String(v))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ASSET_AUTO}>Standard</SelectItem>
                {assets.map((a) => (
                  <SelectItem key={a} value={a}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <p className="text-xs text-zinc-500">
            Das Asset bestimmt die handelbare Schrittweite (Lot-Size).
          </p>
        </div>

        {/* Szenario-Kontostand — ueberschreibt NUR diese Rechnung. */}
        {allowPortfolioOverride ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-portfolio">Kontostand (Szenario)</Label>
            <Input
              id="rc-portfolio"
              type="number"
              inputMode="decimal"
              className={cn(
                numCls,
                scenarioActive && "border-amber-500/60 text-amber-200",
              )}
              value={form.portfolio}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => set("portfolio", e.target.value)}
              placeholder={
                realBalance !== null
                  ? `${fmtUsd(realBalance)} (aus den Settings)`
                  : "leer = Kontostand aus den Settings"
              }
            />
            {scenarioActive ? (
              <Warn tone="amber">
                <p className="font-medium">
                  Szenario-Rechnung — nicht dein echter Kontostand.
                </p>
                <p className="text-xs">
                  Gerechnet wird mit {fmtUsd(num(form.portfolio))} statt{" "}
                  {realBalance !== null
                    ? fmtUsd(realBalance)
                    : "dem Kontostand aus den Settings"}
                  . Der hinterlegte Kontostand bleibt unverändert; ein daraus
                  angelegter Trade nutzt wieder den echten Saldo.
                </p>
              </Warn>
            ) : (
              <p className="text-xs text-zinc-500">
                Leer lassen für den aktuellen Kontostand aus den Settings. Ein
                Wert hier rechnet nur ein Szenario und ändert nichts.
              </p>
            )}
          </div>
        ) : null}
      </div>

      {/* Ergebnis */}
      <div className="flex flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-950 p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-zinc-200">Ergebnis</h3>
          <div className="flex items-center gap-2">
            {scenarioActive ? (
              <span className="inline-flex items-center rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-300">
                Szenario
              </span>
            ) : null}
            {pending ? (
              <Loader2 className="size-4 animate-spin text-zinc-500" />
            ) : null}
          </div>
        </div>

        {error ? (
          <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}

        {!result && !error ? (
          <p className="text-sm text-zinc-500">
            Entry, Stop und Risiko eingeben für die Live-Berechnung.
          </p>
        ) : null}

        {result ? (
          <>
            {/* ---- Warnungen zuerst: nie still eine zu große Position ---- */}
            {result.rounds_to_zero ? (
              <Warn tone="red" icon={<ShieldAlert className="size-4" />}>
                <p className="font-medium">
                  Position rundet auf 0 — nicht handelbar.
                </p>
                <p className="text-xs">
                  Die kleinste handelbare Einheit ({fmtLot(result.min_position_size)}
                  {result.asset ? ` ${result.asset}` : ""}) ist größer als die
                  berechnete Position. Mehr Risiko oder engerer Stop nötig.
                </p>
              </Warn>
            ) : !result.valid_risk ? (
              <Warn tone="red" icon={<ShieldAlert className="size-4" />}>
                <p className="font-medium">
                  Risiko außerhalb deiner Toleranz — nicht ausführen.
                </p>
                <p className="text-xs">
                  Durch die Rundung auf die Schrittweite{" "}
                  {fmtLot(result.min_position_size)} beträgt das tatsächliche
                  Risiko <strong>{fmtUsd(result.adjusted_risk)}</strong> statt{" "}
                  {fmtUsd(result.effective_desired_risk)} (
                  {result.risk_overshoot_pct >= 0 ? "+" : ""}
                  {fmtNum(result.risk_overshoot_pct, 1)} %). Erlaubt ist{" "}
                  {fmtUsd(result.risk_lower_bound)} – {fmtUsd(result.risk_upper_bound)}.
                </p>
                {result.floor_pos_size > 0 ? (
                  <p className="text-xs">
                    Sichere Alternative eine Stufe kleiner:{" "}
                    <strong>{fmtNum(result.floor_pos_size, 8)}</strong> → Risiko{" "}
                    {fmtUsd(result.floor_risk)}
                    {result.floor_valid ? " (im Rahmen)" : ""}.
                  </p>
                ) : null}
              </Warn>
            ) : null}

            {result.leverage_exceeds_max ? (
              <Warn tone="red">
                <p className="font-medium">Leverage über dem Asset-Limit.</p>
                <p className="text-xs">
                  Benötigt {fmtNum(result.exchange_leverage, 0)}×, erlaubt sind
                  maximal {fmtNum(result.max_leverage, 0)}× für{" "}
                  {result.settings_asset ?? "dieses Asset"}.
                </p>
              </Warn>
            ) : null}

            {result.below_min_order_value ? (
              <Warn tone="amber">
                <p className="text-xs">
                  Notional {fmtUsd(result.adjusted_notional)} liegt unter dem
                  Mindest-Ordervolumen von{" "}
                  {fmtUsd(result.min_order_value_usd)} — die Börse würde die
                  Order ablehnen.
                </p>
              </Warn>
            ) : null}

            {result.settings_fallback ? (
              <Warn tone="amber">
                <p className="text-xs">
                  Für <strong>{result.asset}</strong> sind keine Settings
                  hinterlegt — gerechnet wurde mit der{" "}
                  {result.settings_asset}-Schrittweite (
                  {fmtLot(result.min_position_size)}). Das Ergebnis ist
                  möglicherweise nicht platzierbar. Asset in den Settings anlegen.
                </p>
              </Warn>
            ) : null}

            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
                  result.direction === "long"
                    ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                    : "border-red-500/30 bg-red-500/15 text-red-400",
                )}
              >
                {result.direction === "long" ? "Long" : "Short"}
              </span>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
                  result.valid_risk
                    ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                    : "border-red-500/30 bg-red-500/15 text-red-300",
                )}
              >
                {result.valid_risk ? "Risiko im Rahmen" : "Risiko NICHT im Rahmen"}
              </span>
              {result.settings_asset ? (
                <span className="inline-flex items-center rounded-md border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs font-medium text-zinc-300">
                  {result.settings_asset}
                </span>
              ) : null}
            </div>

            <div
              className={cn(
                "rounded-md px-4 py-2",
                blocking ? "bg-red-500/10" : "bg-zinc-900/60",
              )}
            >
              <div className="flex items-baseline justify-between">
                <span className="text-xs uppercase tracking-wide text-zinc-500">
                  Positionsgröße
                </span>
                <span className="font-mono text-lg tabular-nums text-zinc-50">
                  {fmtNum(result.adjusted_pos_size, 8)}
                </span>
              </div>
              <div className="mt-0.5 text-right text-xs text-zinc-500">
                Schrittweite {fmtLot(result.min_position_size)}
              </div>
            </div>

            <div className="divide-y divide-zinc-800/60">
              <Row label="Notional" value={fmtUsd(result.adjusted_notional)} />
              <Row
                label="Implizite Leverage"
                hint="Notional ÷ Kontostand"
                value={`${fmtNum(result.implicit_leverage, 2)}×`}
              />
              <Row
                label="Nötig inkl. Buffer"
                value={`${fmtNum(result.leverage, 1)}×`}
              />
              <Row
                label="Einzustellen an der Börse"
                hint={
                  result.max_leverage != null
                    ? `max ${fmtNum(result.max_leverage, 0)}×`
                    : undefined
                }
                strong
                value={
                  result.exchange_leverage != null
                    ? `${fmtNum(result.exchange_leverage, 0)}×`
                    : "—"
                }
              />
              <Row
                label="Erwarteter Verlust (ohne Fees)"
                value={fmtUsd(result.adjusted_exp_loss)}
              />
              <Row label="Fees" value={fmtUsd(result.adjusted_fees)} />
              <Row
                label="Risiko gesamt"
                strong
                value={fmtUsd(result.adjusted_risk)}
              />
              <Row
                label="Ziel-Risiko"
                value={`${fmtUsd(result.effective_desired_risk)} (${fmtPct(
                  result.risk_pct / 100,
                )})`}
              />
              <Row
                label="Erlaubter Bereich"
                value={`${fmtUsd(result.risk_lower_bound)} – ${fmtUsd(
                  result.risk_upper_bound,
                )}`}
              />
              <Row label="Preis-Move" value={fmtNum(result.price_move, 2)} />
              <Row
                label="Portfolio"
                hint={scenarioActive ? "(Szenario)" : undefined}
                value={fmtUsd(result.portfolio_size)}
              />
            </div>

            {actionLabel && onAction ? (
              <Button
                className="mt-2"
                disabled={actionPending}
                variant={blocking ? "outline" : "default"}
                onClick={() => onAction(form, result)}
              >
                {actionPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : null}
                {actionLabel}
                {blocking ? " (trotz Warnung)" : ""}
              </Button>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
