"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import {
  RiskCalculator,
  defaultRiskForm,
  type RiskFormValues,
} from "@/components/risk-calculator";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, createLiveTrade, getSystems } from "@/lib/api";
import type {
  LiveTradeCreatePayload,
  RiskCalcResponse,
  SystemSummary,
} from "@/lib/types";

// Systeme sind der Normalfall; der freie Trade ist eine bewusste Option
// (z. B. diskretionaerer Trade ausserhalb der Systeme). Ohne System geht
// system_id: null ins Backend und das Asset ist frei waehlbar.
const NO_SYSTEM = "__none__";
const NO_SYSTEM_LABEL = "Ohne System (freier Trade)";

function NewLiveTradeFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Prefill aus Query (z. B. „Als Trade übernehmen" von /risk).
  const [form, setForm] = useState<RiskFormValues>(() => {
    // Nur tatsächlich vorhandene Query-Werte übernehmen — undefined würde
    // die Defaults von defaultRiskForm überschreiben.
    const overrides: Partial<RiskFormValues> = {};
    const entry = searchParams.get("entry");
    const stop = searchParams.get("stop");
    const risk = searchParams.get("risk");
    const mode = searchParams.get("mode");
    const modifier = searchParams.get("modifier");
    const venue = searchParams.get("venue");
    const asset = searchParams.get("asset");
    if (entry !== null) overrides.entry = entry;
    if (stop !== null) overrides.stop = stop;
    if (risk !== null) overrides.risk = risk;
    if (mode === "usd" || mode === "pct") overrides.riskMode = mode;
    if (modifier !== null) overrides.modifier = modifier;
    if (venue !== null && venue !== "") overrides.venueId = Number(venue);
    if (asset !== null) overrides.asset = asset;
    return defaultRiskForm(overrides);
  });

  const [systems, setSystems] = useState<SystemSummary[]>([]);
  const [systemId, setSystemId] = useState<number | null>(() => {
    const s = searchParams.get("system");
    return s !== null && s !== "" ? Number(s) : null;
  });
  const [systemsError, setSystemsError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystems()
      .then((r) => setSystems(r.items))
      .catch((err) =>
        setSystemsError(
          err instanceof ApiError && err.status === 0
            ? "Backend nicht erreichbar."
            : "Systeme konnten nicht geladen werden.",
        ),
      );
  }, []);

  const sortedSystems = useMemo(
    () => [...systems].sort((a, b) => a.name.localeCompare(b.name)),
    [systems],
  );

  // base-ui rendert in <Select.Value> den rohen value (hier: die System-ID),
  // solange dem Root kein `items`-Mapping gegeben wird.
  const systemItems = useMemo(() => {
    const map: Record<string, string> = { [NO_SYSTEM]: NO_SYSTEM_LABEL };
    for (const s of sortedSystems) map[String(s.id)] = s.name;
    return map;
  }, [sortedSystems]);

  // Das gewählte System gibt sein Asset vor (fast immer auf genau ein Asset
  // backtestet). Bindet die richtige Schrittweite schon in der Vorschau.
  const selectedSystem = useMemo(
    () => systems.find((s) => s.id === systemId) ?? null,
    [systems, systemId],
  );
  const lockedAsset = selectedSystem?.asset?.trim() || null;

  useEffect(() => {
    if (lockedAsset) {
      setForm((prev) =>
        prev.asset === lockedAsset ? prev : { ...prev, asset: lockedAsset },
      );
    }
  }, [lockedAsset]);

  async function handleCreate(f: RiskFormValues, _result: RiskCalcResponse) {
    setPending(true);
    setError(null);
    try {
      const riskValue = Number(f.risk);
      const payload: LiveTradeCreatePayload = {
        // null = freier Trade ohne System-Zuordnung.
        system_id: systemId,
        asset: f.asset.trim() || undefined,
        planned_entry: Number(f.entry),
        planned_stop: Number(f.stop),
        risk_modifier: Number(f.modifier),
        venue_id: f.venueId ?? undefined,
        run_risk_calc: true,
      };
      if (f.riskMode === "usd") payload.desired_risk_usd = riskValue;
      else payload.risk_pct = riskValue;
      const created = await createLiveTrade(payload);
      router.push(`/live/${created.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : "Trade konnte nicht angelegt werden.",
      );
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-8 py-4">
      <div className="flex flex-col gap-3">
        <Link
          href="/live"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-300"
        >
          <ArrowLeft className="size-4" />
          Zurück zu Live-Trading
        </Link>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            Neuer Trade
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            System wählen, Risk berechnen, Trade anlegen. Ohne System entsteht
            ein freier Trade.
          </p>
        </div>
      </div>

      {/* System-Auswahl */}
      <div className="flex flex-col gap-1.5">
        <Label>System</Label>
        <Select
          items={systemItems}
          value={systemId !== null ? String(systemId) : NO_SYSTEM}
          onValueChange={(v) => {
            setSystemId(v === NO_SYSTEM ? null : Number(v));
            setError(null);
          }}
        >
          <SelectTrigger className="sm:max-w-sm">
            <SelectValue placeholder="System auswählen…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_SYSTEM}>{NO_SYSTEM_LABEL}</SelectItem>
            {sortedSystems.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {systemsError ? (
          <p className="text-xs text-red-400">{systemsError}</p>
        ) : null}
        {systemId === null ? (
          <p className="text-xs text-zinc-500">
            Freier Trade: keinem System zugeordnet — er taucht in keiner
            System-Live-Statistik auf, zählt aber auf den Kontostand. Das Asset
            wählst du unten selbst.
          </p>
        ) : null}
      </div>

      {/* Risk-Rechner */}
      <RiskCalculator
        form={form}
        onFormChange={setForm}
        actionLabel="Trade anlegen"
        onAction={(f, result) => void handleCreate(f, result)}
        actionPending={pending}
        assetLockedTo={lockedAsset}
      />

      {pending ? (
        <p className="flex items-center gap-2 text-sm text-zinc-400">
          <Loader2 className="size-4 animate-spin" />
          Trade wird angelegt…
        </p>
      ) : null}

      {error ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export default function NewLiveTradePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center gap-2 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Lade…
        </div>
      }
    >
      <NewLiveTradeFlow />
    </Suspense>
  );
}
