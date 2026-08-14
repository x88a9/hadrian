"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  RiskCalculator,
  defaultRiskForm,
  type RiskFormValues,
} from "@/components/risk-calculator";
import type { RiskCalcResponse } from "@/lib/types";

export default function RiskPage() {
  const router = useRouter();
  const [form, setForm] = useState<RiskFormValues>(() => defaultRiskForm());

  // "Als Trade übernehmen": Formularwerte als Query an den Neuer-Trade-Flow.
  function toNewTrade(f: RiskFormValues, _result: RiskCalcResponse) {
    const params = new URLSearchParams();
    if (f.entry) params.set("entry", f.entry);
    if (f.stop) params.set("stop", f.stop);
    if (f.risk) params.set("risk", f.risk);
    params.set("mode", f.riskMode);
    if (f.modifier) params.set("modifier", f.modifier);
    if (f.venueId !== null) params.set("venue", String(f.venueId));
    if (f.asset.trim()) params.set("asset", f.asset.trim());
    router.push(`/live/new?${params.toString()}`);
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
          Risk-Rechner
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Positionsgröße, Notional und Leverage aus Entry, Stop und Wunschrisiko —
          netto nach Fees. Ohne Trade nutzbar; aus dem Ergebnis heraus direkt einen
          Trade anlegen.
        </p>
      </div>

      <RiskCalculator
        form={form}
        onFormChange={setForm}
        actionLabel="Als Trade übernehmen"
        onAction={toNewTrade}
        // Nur hier: Szenario-Kontostand. Auf /live/new entsteht ein realer
        // Trade — der muss immer gegen den echten Saldo gerechnet werden.
        allowPortfolioOverride
      />
    </main>
  );
}
