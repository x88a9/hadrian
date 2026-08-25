/**
 * The blocks helpers, checked against the real validator.
 *
 * `blocks.test.ts` proves the helpers behave as designed; this proves the
 * design agrees with the backend. Those are different claims, and the gap
 * between them is exactly the drift this whole feature was shaped to avoid: a
 * designer that offers something the schema refuses, or quietly stops offering
 * something it allows. Nothing else in the repository catches that — the
 * Python suite never sees this code, and the unit tests never see the schema.
 *
 * Needs the API running. Skips cleanly when it is not, the same way the
 * backend's own integration tests skip without Postgres, so `npm run test`
 * stays useful on a machine with nothing else started:
 *
 *     cd backend && DATABASE_URL=... .venv/bin/uvicorn app.main:app --port 8000
 *     HADRIAN_API=http://127.0.0.1:8000 npm run test
 */
import { describe, expect, it } from "vitest";
import * as B from "./blocks";
import type { StrategyDefinition } from "./types";

const API = process.env.HADRIAN_API ?? "http://127.0.0.1:8000";

/**
 * Probed at module scope, not in `beforeAll`.
 *
 * `it.skipIf` is evaluated while the file is being collected, which happens
 * before any hook runs — a flag set in `beforeAll` is still false by the time
 * the decision is made, and every case skips even with the API up. Top-level
 * await resolves before collection, so the flag is real.
 */
const reachable = await (async () => {
  try {
    const response = await fetch(`${API}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    return response.ok;
  } catch {
    return false;
  }
})();

if (!reachable) {
  console.warn(
    `[blocks.contract] API not reachable at ${API}; skipping the contract ` +
      `checks. Start the backend and set HADRIAN_API to run them.`,
  );
}

const BASE: StrategyDefinition = {
  schema_version: 1,
  name: "Crosscheck",
  description: "round-tripped through the blocks helpers",
  asset: "BTC",
  timeframe: "1h",
  direction: "long",
  rules: "declarative",
  python_source: null,
  parameters: { fast: { value: 5, lo: 3, hi: 9, step: 2, description: null } },
  indicators: [
    { id: "fast_sma", kind: "sma", source: "close", params: { period: { param: "fast" } } },
    { id: "slow_sma", kind: "sma", source: "close", params: { period: 20 } },
    { id: "atr14", kind: "atr", source: "close", params: { period: 14 } },
  ],
  entry_long: {
    node: "compare",
    left: { op: "indicator", id: "fast_sma", offset: 0 },
    cmp: "cross_above",
    right: { op: "indicator", id: "slow_sma", offset: 0 },
  },
  entry_short: null,
  exit_long: {
    node: "any",
    terms: [
      { node: "compare", left: { op: "position", field: "bars_held" }, cmp: ">", right: { op: "const", value: 48 } },
      { node: "compare", left: { op: "price", field: "close", offset: 0 }, cmp: "<", right: { op: "indicator", id: "slow_sma", offset: 1 } },
    ],
  },
  exit_short: null,
  filters: [
    { node: "compare", left: { op: "price", field: "close", offset: 0 }, cmp: ">", right: { op: "const", value: 1000 } },
  ],
  risk: {
    stop: { kind: "atr_multiple", value: 2, indicator_id: "atr14", breakeven_at_r: 1, trail_atr_multiple: null },
    target: { kind: "r_multiple", value: 3, indicator_id: null },
    max_bars_held: 200,
    max_concurrent_positions: 1,
  },
  costs: { entry_fee_pct: 0.000144, exit_fee_pct: 0.000432, slippage_pct: 0, funding_pct_per_day: 0 },
};

async function validate(d: StrategyDefinition) {
  const r = await fetch(`${API}/strategies/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ definition: d }),
  });
  return r.json();
}

describe("blocks helpers against the real validator", () => {
  it.skipIf(!reachable)("the fixture itself is accepted by the backend", async () => {
    const v = await validate(BASE);
    expect(v.errors).toEqual([]);
    expect(v.ok).toBe(true);
  });

  it("a full read-out and write-back round trip is byte-identical", () => {
    let d: StrategyDefinition = JSON.parse(JSON.stringify(BASE));
    const m = B.getMetadata(d);
    d = B.setMetadata(d, m);
    d = B.setParameters(d, d.parameters);
    d = B.setIndicators(d, d.indicators);
    d = B.setEntryLong(d, d.entry_long);
    d = B.setEntryShort(d, d.entry_short);
    d = B.setExitLong(d, d.exit_long);
    d = B.setExitShort(d, d.exit_short);
    d = B.setFilters(d, d.filters);
    d = B.setRisk(d, d.risk);
    d = B.setCosts(d, d.costs);
    expect(d).toEqual(BASE);
  });

  it.skipIf(!reachable)("the round-tripped definition is still accepted by the backend", async () => {
    let d: StrategyDefinition = JSON.parse(JSON.stringify(BASE));
    d = B.setRisk(d, d.risk);
    d = B.setIndicators(d, d.indicators);
    const v = await validate(d);
    expect(v.errors).toEqual([]);
  });

  it.skipIf(!reachable)("renaming an indicator repoints every reference the backend checks", async () => {
    const renamed = B.renameIndicatorId(BASE, "slow_sma", "sma_slow");
    const v = await validate(renamed);
    expect(v.errors).toEqual([]);
    expect(JSON.stringify(renamed)).not.toContain("slow_sma");
    expect(JSON.stringify(renamed)).toContain("sma_slow");
  });

  it.skipIf(!reachable)("renaming a parameter repoints its references", async () => {
    const renamed = B.renameParameter(BASE, "fast", "schnell");
    const v = await validate(renamed);
    expect(v.errors).toEqual([]);
    expect(renamed.indicators[0].params.period).toEqual({ param: "schnell" });
  });

  it.skipIf(!reachable)("switching to a crossing comparator strips offsets the backend would reject", async () => {
    const withOffset: StrategyDefinition = JSON.parse(JSON.stringify(BASE));
    withOffset.entry_long = {
      node: "compare",
      left: { op: "indicator", id: "fast_sma", offset: 2 },
      cmp: ">",
      right: { op: "indicator", id: "slow_sma", offset: 3 },
    };
    // Backend refuses an offset next to a crossing.
    const naive = JSON.parse(JSON.stringify(withOffset));
    naive.entry_long.cmp = "cross_above";
    expect((await validate(naive)).ok).toBe(false);

    const fixed: StrategyDefinition = JSON.parse(JSON.stringify(withOffset));
    fixed.entry_long = B.setComparator(fixed.entry_long as never, "cross_above") as never;
    const v = await validate(fixed);
    expect(v.errors).toEqual([]);
  });

  it.skipIf(!reachable)("the vocabulary the designer builds from is reachable and complete", async () => {
    const vocab = await (await fetch(`${API}/strategies/schema`)).json();
    expect(vocab.indicators.length).toBeGreaterThan(0);
    const slots = Object.fromEntries(
      vocab.rule_slots.map((s: { slot: string; allows_position: boolean }) => [s.slot, s.allows_position]),
    );
    expect(slots.entry_long).toBe(false);
    expect(slots.exit_long).toBe(true);
  });
});
