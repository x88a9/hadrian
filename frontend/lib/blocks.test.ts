import { describe, expect, it } from "vitest";

import {
  IndicatorRenameError,
  addTermAtPath,
  defaultBoolNode,
  defaultComparison,
  defaultConstOperand,
  defaultIndicatorOperand,
  defaultOperand,
  defaultPositionOperand,
  defaultPriceOperand,
  getMetadata,
  isCrossingComparator,
  removeTermAtPath,
  renameIndicatorId,
  renameParameter,
  setComparator,
  setCosts,
  setDirection,
  setEntryLong,
  setEntryShort,
  setExitLong,
  setExitShort,
  setFilters,
  setIndicators,
  setMetadata,
  setParameters,
  setRisk,
  sweepGridLabel,
  sweepValues,
} from "./blocks";
import type { Comparison, Condition, StrategyDefinition } from "./types";

// A representative definition exercising every field the round-trip test
// cares about: a nested condition tree, a filter, a parameter reference used
// in risk.stop, an indicator referenced from a rule and from risk.target, and
// the "boring" scalar fields (schema_version, python_source: null,
// description) that are easy to accidentally drop.
function representativeDefinition(): StrategyDefinition {
  return {
    schema_version: 1,
    name: "Test Strategy",
    description: "A representative fixture",
    asset: "BTC",
    timeframe: "1h",
    direction: "both",
    rules: "declarative",
    python_source: null,
    parameters: {
      fast: { value: 10, lo: 5, hi: 20, step: 5, description: "fast period" },
      stop_mult: { value: 1.5, lo: null, hi: null, step: null, description: null },
    },
    indicators: [
      { id: "sma_fast", kind: "sma", source: "close", params: { period: 10 } },
      { id: "atr14", kind: "atr", source: "close", params: { period: 14 } },
    ],
    entry_long: {
      node: "all",
      terms: [
        {
          node: "compare",
          left: { op: "indicator", id: "sma_fast", offset: 0 },
          cmp: ">",
          right: { op: "price", field: "close", offset: 1 },
        },
        {
          node: "any",
          terms: [
            {
              node: "compare",
              left: { op: "price", field: "close", offset: 0 },
              cmp: "cross_above",
              right: { op: "indicator", id: "sma_fast", offset: 0 },
            },
          ],
        },
      ],
    },
    entry_short: {
      node: "compare",
      left: { op: "price", field: "close", offset: 0 },
      cmp: "<",
      right: { op: "indicator", id: "sma_fast", offset: 0 },
    },
    exit_long: null,
    exit_short: null,
    filters: [
      {
        node: "compare",
        left: { op: "indicator", id: "atr14", offset: 0 },
        cmp: ">",
        right: { op: "const", value: { param: "stop_mult" } },
      },
    ],
    risk: {
      stop: {
        kind: "atr_multiple",
        value: { param: "stop_mult" },
        indicator_id: "atr14",
        breakeven_at_r: 1,
        trail_atr_multiple: null,
      },
      target: { kind: "indicator", value: 1, indicator_id: "atr14" },
      max_bars_held: 50,
      max_concurrent_positions: 1,
    },
    costs: {
      entry_fee_pct: 0.000144,
      exit_fee_pct: 0.000432,
      slippage_pct: 0,
      funding_pct_per_day: 0,
    },
  };
}

describe("round trip: definition -> blocks state -> definition", () => {
  it("reading each section out and writing it back unchanged preserves the whole definition", () => {
    const original = representativeDefinition();
    const frozen = JSON.parse(JSON.stringify(original));

    let next = original;
    next = setMetadata(next, getMetadata(next));
    next = setParameters(next, next.parameters);
    next = setIndicators(next, next.indicators);
    next = setEntryLong(next, next.entry_long);
    next = setEntryShort(next, next.entry_short);
    next = setExitLong(next, next.exit_long);
    next = setExitShort(next, next.exit_short);
    next = setFilters(next, next.filters);
    next = setRisk(next, next.risk);
    next = setCosts(next, next.costs);

    expect(next).toEqual(frozen);
    // The input itself must never be mutated by any of the above.
    expect(original).toEqual(frozen);
    // Fields no section setter above ever touches must still be exactly there.
    expect(next.schema_version).toBe(1);
    expect(next.python_source).toBeNull();
    expect(next.description).toBe("A representative fixture");
  });
});

describe("condition tree editing", () => {
  it("adds a term to a nested group without mutating the input", () => {
    const root = representativeDefinition().entry_long as Condition;
    const before = JSON.parse(JSON.stringify(root));
    const newTerm = defaultComparison();

    const next = addTermAtPath(root, [1], newTerm); // path [1] = the nested "any" group

    expect(root).toEqual(before); // input untouched
    if (next.node === "compare") throw new Error("expected a bool node");
    const group = next.terms[1];
    if (group.node === "compare") throw new Error("expected the nested group");
    expect(group.terms).toHaveLength(2);
    expect(group.terms[1]).toEqual(newTerm);
    // Sibling term (index 0) keeps its identity — untouched branch reused.
    if (root.node === "compare") throw new Error("expected a bool node");
    expect(next.terms[0]).toBe(root.terms[0]);
  });

  it("removes a term from a nested group without mutating the input", () => {
    const root: Condition = {
      node: "all",
      terms: [defaultComparison(), defaultComparison(), defaultComparison()],
    };
    const before = JSON.parse(JSON.stringify(root));

    const next = removeTermAtPath(root, [], 1);

    expect(root).toEqual(before);
    if (next.node === "compare") throw new Error("expected a bool node");
    expect(next.terms).toHaveLength(2);
  });
});

describe("indicator id rename", () => {
  it("repoints every reference: rules, filters, risk.stop and risk.target", () => {
    const definition = representativeDefinition();
    const renamed = renameIndicatorId(definition, "atr14", "atr_slow");

    expect(renamed.indicators.map((i) => i.id)).toContain("atr_slow");
    expect(renamed.indicators.some((i) => i.id === "atr14")).toBe(false);
    expect(renamed.risk.stop.indicator_id).toBe("atr_slow");
    expect(renamed.risk.target?.indicator_id).toBe("atr_slow");

    const filterLeft = renamed.filters[0];
    if (filterLeft.node !== "compare") throw new Error("expected a comparison");
    expect(filterLeft.left).toEqual({ op: "indicator", id: "atr_slow", offset: 0 });

    // entry_short references sma_fast, not atr14 — must be untouched.
    expect(renamed.entry_short).toEqual(definition.entry_short);
    // Original definition must not have been mutated.
    expect(definition.indicators.some((i) => i.id === "atr14")).toBe(true);
  });

  it("refuses a rename onto an id already used by a different indicator", () => {
    const definition = representativeDefinition();
    expect(() => renameIndicatorId(definition, "atr14", "sma_fast")).toThrow(
      IndicatorRenameError,
    );
  });

  it("is a no-op when renaming to the same id", () => {
    const definition = representativeDefinition();
    expect(renameIndicatorId(definition, "atr14", "atr14")).toBe(definition);
  });
});

describe("parameter rename", () => {
  it("repoints references in const operands, indicator params and risk", () => {
    const definition = representativeDefinition();
    const renamed = renameParameter(definition, "stop_mult", "stop_multiple");

    expect(renamed.parameters).toHaveProperty("stop_multiple");
    expect(renamed.parameters).not.toHaveProperty("stop_mult");
    expect(renamed.risk.stop.value).toEqual({ param: "stop_multiple" });

    const filterCond = renamed.filters[0];
    if (filterCond.node !== "compare") throw new Error("expected a comparison");
    expect(filterCond.right).toEqual({ op: "const", value: { param: "stop_multiple" } });
  });
});

describe("comparator switching", () => {
  it("strips offsets when switching to a crossing comparator", () => {
    const cmp: Comparison = {
      node: "compare",
      left: { op: "price", field: "close", offset: 3 },
      cmp: ">",
      right: { op: "indicator", id: "sma_fast", offset: 2 },
    };

    const next = setComparator(cmp, "cross_above");

    expect(isCrossingComparator("cross_above")).toBe(true);
    expect(next.left).toEqual({ op: "price", field: "close", offset: 0 });
    expect(next.right).toEqual({ op: "indicator", id: "sma_fast", offset: 0 });
    // Input untouched.
    expect(cmp.left).toEqual({ op: "price", field: "close", offset: 3 });
  });

  it("leaves offsets alone for a non-crossing comparator", () => {
    const cmp: Comparison = {
      node: "compare",
      left: { op: "price", field: "close", offset: 3 },
      cmp: "cross_above",
      right: { op: "const", value: 1 },
    };
    const next = setComparator(cmp, ">=");
    expect(next.left).toEqual({ op: "price", field: "close", offset: 3 });
  });
});

describe("default operand shapes", () => {
  it("builds a schema-shaped default for each operand kind", () => {
    expect(defaultOperand("price")).toEqual({ op: "price", field: "close", offset: 0 });
    expect(defaultOperand("indicator", "sma_fast")).toEqual({
      op: "indicator",
      id: "sma_fast",
      offset: 0,
    });
    expect(defaultOperand("const")).toEqual({ op: "const", value: 0 });
    expect(defaultOperand("position")).toEqual({ op: "position", field: "bars_held" });

    expect(defaultPriceOperand().offset).toBeGreaterThanOrEqual(0);
    expect(defaultIndicatorOperand().offset).toBeGreaterThanOrEqual(0);
    expect(typeof defaultConstOperand().value).toBe("number");
    expect(defaultPositionOperand().field).toBe("bars_held");
  });

  it("builds a valid default bool node with at least one term", () => {
    const node = defaultBoolNode("all");
    expect(node.terms.length).toBeGreaterThanOrEqual(1);
    const notNode = defaultBoolNode("not");
    expect(notNode.terms).toHaveLength(1);
  });
});

describe("sweep grid", () => {
  it("computes the same grid as ParameterSpec.sweep_values() in the backend", () => {
    expect(sweepValues({ value: 3, lo: 3, hi: 9, step: 2, description: null })).toEqual([
      3, 5, 7, 9,
    ]);
    expect(sweepGridLabel({ value: 3, lo: 3, hi: 9, step: 2, description: null })).toBe(
      "4 Werte: 3, 5, 7, 9",
    );
  });

  it("contributes only the current value when no range is declared", () => {
    expect(sweepValues({ value: 42, lo: null, hi: null, step: null, description: null })).toEqual([
      42,
    ]);
  });
});

describe("direction changes", () => {
  it("clears entry_short and requires entry_long when switching to 'long'", () => {
    const definition = representativeDefinition();
    const next = setDirection(definition, "long");
    expect(next.entry_short).toBeNull();
    expect(next.entry_long).not.toBeNull();
  });

  it("fills in a default entry_short when switching to 'both' from 'long'", () => {
    const definition = setDirection(representativeDefinition(), "long");
    const next = setDirection(definition, "both");
    expect(next.entry_short).not.toBeNull();
    expect(next.entry_long).not.toBeNull();
  });
});
