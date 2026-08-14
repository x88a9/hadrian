"use client";

import { useEffect, useMemo, useState } from "react";

import { MonteCarloPanel } from "@/components/montecarlo-panel";
import { TopographyHeatmap } from "@/components/topography-heatmap";
import { WalkForwardPanel } from "@/components/walkforward-panel";
import { getTopography } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TopographyResponse, Trade } from "@/lib/types";

type TabKey = "topography" | "walkforward" | "montecarlo";

const TAB_LABEL: Record<TabKey, string> = {
  topography: "Topographie",
  walkforward: "Walk-Forward",
  montecarlo: "Monte-Carlo",
};

interface QuantSectionProps {
  systemId: number;
  trades: Trade[];
}

export function QuantSection({ systemId, trades }: QuantSectionProps) {
  const [topo, setTopo] = useState<TopographyResponse | null>(null);
  const [topoLoaded, setTopoLoaded] = useState(false);
  const [active, setActive] = useState<TabKey | null>(null);

  // Topographie einmal initial laden (fuer die Sichtbarkeitsentscheidung).
  useEffect(() => {
    let alive = true;
    setTopoLoaded(false);
    setTopo(null);
    getTopography(systemId)
      .then((r) => {
        if (alive) setTopo(r);
      })
      .catch(() => {
        if (alive) setTopo(null);
      })
      .finally(() => {
        if (alive) setTopoLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [systemId]);

  // Sichtbarkeit je Tab aus bereits geladenen Trades bzw. Topographie.
  const hasWf = useMemo(
    () =>
      trades.some(
        (t) =>
          t.trade_datetime !== null &&
          typeof t.r_value === "number" &&
          !Number.isNaN(t.r_value),
      ),
    [trades],
  );
  const rCount = useMemo(
    () =>
      trades.filter(
        (t) => typeof t.r_value === "number" && !Number.isNaN(t.r_value),
      ).length,
    [trades],
  );
  const hasMc = rCount >= 10;
  const hasTopo = (topo?.grids.length ?? 0) > 0;

  const tabs = useMemo<TabKey[]>(() => {
    const t: TabKey[] = [];
    if (hasTopo) t.push("topography");
    if (hasWf) t.push("walkforward");
    if (hasMc) t.push("montecarlo");
    return t;
  }, [hasTopo, hasWf, hasMc]);

  // Aktiven Tab auf ersten verfuegbaren setzen bzw. korrigieren.
  useEffect(() => {
    if (tabs.length === 0) {
      setActive(null);
      return;
    }
    setActive((cur) => (cur && tabs.includes(cur) ? cur : tabs[0]));
  }, [tabs]);

  // Solange Topographie unbekannt UND keine WF/MC-Tabs feststehen: nichts rendern.
  if (!topoLoaded && !hasWf && !hasMc) return null;
  if (tabs.length === 0) return null;

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
        Quant-Analytik
      </h2>

      {/* Tab-Strip (selbstgebaut). */}
      <div className="mb-4 inline-flex overflow-hidden rounded-lg border border-zinc-800">
        {tabs.map((t, i) => (
          <button
            key={t}
            type="button"
            onClick={() => setActive(t)}
            className={cn(
              "h-9 px-4 text-sm font-medium transition-colors",
              i > 0 && "border-l border-zinc-800",
              active === t
                ? "bg-zinc-800 text-zinc-100"
                : "bg-zinc-900/40 text-zinc-400 hover:text-zinc-200",
            )}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/20 p-4">
        {active === "topography" && topo && (
          <TopographyHeatmap grids={topo.grids} preGate={topo.pre_gate} />
        )}
        {active === "walkforward" && <WalkForwardPanel systemId={systemId} />}
        {active === "montecarlo" && <MonteCarloPanel systemId={systemId} />}
      </div>
    </section>
  );
}
