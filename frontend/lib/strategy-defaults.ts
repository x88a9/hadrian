// Scaffolding for a brand-new strategy definition. Both branches produce a
// definition that already passes backend validation (see
// backend/app/strategy/definition.py's StrategyDefinition._validate), so
// "New Strategy" always opens on something runnable rather than an empty
// shell the designer would immediately reject.

import {
  STRATEGY_SCHEMA_VERSION,
  type StrategyDefinition,
} from "./types";

export interface NewStrategyOptions {
  name: string;
  description?: string | null;
  asset: string;
  timeframe: string;
  direction: "long" | "short" | "both";
}

const DEFAULT_COSTS = {
  entry_fee_pct: 0.000144,
  exit_fee_pct: 0.000432,
  slippage_pct: 0,
  funding_pct_per_day: 0,
};

export function defaultDeclarativeDefinition(
  opts: NewStrategyOptions,
): StrategyDefinition {
  const { name, description, asset, timeframe, direction } = opts;

  // Trivial placeholder signal (last close vs. the one before it) so the
  // definition is valid and backtestable without requiring the author to
  // wire up indicators first.
  const longEntry = {
    node: "compare" as const,
    left: { op: "price" as const, field: "close" as const, offset: 0 },
    cmp: ">" as const,
    right: { op: "price" as const, field: "close" as const, offset: 1 },
  };
  const shortEntry = {
    node: "compare" as const,
    left: { op: "price" as const, field: "close" as const, offset: 0 },
    cmp: "<" as const,
    right: { op: "price" as const, field: "close" as const, offset: 1 },
  };

  return {
    schema_version: STRATEGY_SCHEMA_VERSION,
    name,
    description: description ?? null,
    asset,
    timeframe,
    direction,
    rules: "declarative",
    python_source: null,
    parameters: {
      stop_pct: {
        value: 1.0,
        lo: 0.5,
        hi: 3.0,
        step: 0.5,
        description: "Stop-Loss in Prozent vom Entry",
      },
    },
    indicators: [],
    entry_long: direction === "long" || direction === "both" ? longEntry : null,
    entry_short:
      direction === "short" || direction === "both" ? shortEntry : null,
    exit_long: null,
    exit_short: null,
    filters: [],
    risk: {
      stop: { kind: "percent", value: { param: "stop_pct" } },
      target: { kind: "r_multiple", value: 2.0 },
      max_bars_held: null,
      max_concurrent_positions: 1,
    },
    costs: { ...DEFAULT_COSTS },
  };
}

// Illustrative starter — mirrors the example in
// backend/app/strategy/interface.py's Strategy docstring. The sandbox's
// allowed-import set is whatever it preloads before the audit hook goes up,
// so this deliberately does not add an explicit `import` line; adjust once
// the exact sandbox namespace is confirmed.
const PYTHON_TEMPLATE = `class MyStrategy(Strategy):
    name = "New Strategy"
    asset = "{{ASSET}}"
    timeframe = "{{TIMEFRAME}}"
    direction = "{{DIRECTION}}"

    indicators = [
        {"id": "sma_fast", "kind": "sma", "params": {"period": 10}},
        {"id": "sma_slow", "kind": "sma", "params": {"period": 30}},
    ]

    risk = {
        "stop": {"kind": "percent", "value": 1.0},
        "target": {"kind": "r_multiple", "value": 2.0},
    }

    def on_bar(self, ctx):
        if not ctx.indicator_ready("sma_fast", "sma_slow"):
            return None
        if ctx.position is None:
            if ctx.indicator("sma_fast") > ctx.indicator("sma_slow"):
                return Signal.enter_long()
        return None
`;

export function defaultPythonDefinition(
  opts: NewStrategyOptions,
): StrategyDefinition {
  const { name, description, asset, timeframe, direction } = opts;
  const source = PYTHON_TEMPLATE.replace("{{ASSET}}", asset)
    .replace("{{TIMEFRAME}}", timeframe)
    .replace("{{DIRECTION}}", direction === "both" ? "long" : direction);

  return {
    schema_version: STRATEGY_SCHEMA_VERSION,
    name,
    description: description ?? null,
    asset,
    timeframe,
    direction,
    rules: "python",
    python_source: source,
    parameters: {},
    indicators: [],
    entry_long: null,
    entry_short: null,
    exit_long: null,
    exit_short: null,
    filters: [],
    risk: {
      stop: { kind: "percent", value: 1.0 },
      target: { kind: "r_multiple", value: 2.0 },
      max_bars_held: null,
      max_concurrent_positions: 1,
    },
    costs: { ...DEFAULT_COSTS },
  };
}
