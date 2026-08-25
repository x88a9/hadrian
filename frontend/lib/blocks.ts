// Pure, framework-free helpers for the visual block designer (the "Blöcke"
// tab). Every function here treats StrategyDefinition as immutable: read a
// slice, write a slice back with spread + replace, never rebuild the whole
// object. That is what keeps a definition lossless as it moves
// JSON -> blocks -> JSON: a function that does not know about a field never
// touches it.
//
// No React, no DOM — this file is testable with plain vitest (see
// blocks.test.ts).

import {
  isParamRef,
  type BoolNode,
  type Comparator,
  type Comparison,
  type Condition,
  type ConstOperand,
  type CostSpec,
  type IndicatorKind,
  type IndicatorOperand,
  type IndicatorSpec,
  type Operand,
  type ParameterSpec,
  type PositionOperand,
  type PriceOperand,
  type RiskSpec,
  type StopSpec,
  type StrategyDefinition,
  type StrategyNumber,
  type TargetSpec,
} from "./types";

// --------------------------------------------------------------------------
// Section getters/setters — the "windows" the block cards edit through.
// Each setter only ever replaces its own field, so editing one section can
// never disturb another (or python_source, schema_version, description, …).
// --------------------------------------------------------------------------

export interface MetadataFields {
  asset: string;
  timeframe: string;
  direction: StrategyDefinition["direction"];
  description: string | null | undefined;
}

export function getMetadata(definition: StrategyDefinition): MetadataFields {
  return {
    asset: definition.asset,
    timeframe: definition.timeframe,
    direction: definition.direction,
    description: definition.description,
  };
}

export function setMetadata(
  definition: StrategyDefinition,
  patch: Partial<MetadataFields>,
): StrategyDefinition {
  return { ...definition, ...patch };
}

// Changing direction can make the current entry rules invalid ("direction is
// 'long' but entry_short is set" / "... entry_long is unset"), so this keeps
// entry_long/entry_short consistent with the new direction rather than
// leaving that to a validate-then-fix round trip. Only declarative
// definitions carry entry_* trees at all.
export function setDirection(
  definition: StrategyDefinition,
  direction: StrategyDefinition["direction"],
): StrategyDefinition {
  if (definition.rules !== "declarative") {
    return { ...definition, direction };
  }
  const wantsLong = direction === "long" || direction === "both";
  const wantsShort = direction === "short" || direction === "both";
  return {
    ...definition,
    direction,
    entry_long: wantsLong ? (definition.entry_long ?? defaultComparison()) : null,
    entry_short: wantsShort ? (definition.entry_short ?? defaultComparison()) : null,
  };
}

export function setParameters(
  definition: StrategyDefinition,
  parameters: Record<string, ParameterSpec>,
): StrategyDefinition {
  return { ...definition, parameters };
}

export function setIndicators(
  definition: StrategyDefinition,
  indicators: IndicatorSpec[],
): StrategyDefinition {
  return { ...definition, indicators };
}

export function setEntryLong(
  definition: StrategyDefinition,
  cond: Condition | null | undefined,
): StrategyDefinition {
  return { ...definition, entry_long: cond ?? null };
}

export function setEntryShort(
  definition: StrategyDefinition,
  cond: Condition | null | undefined,
): StrategyDefinition {
  return { ...definition, entry_short: cond ?? null };
}

export function setExitLong(
  definition: StrategyDefinition,
  cond: Condition | null | undefined,
): StrategyDefinition {
  return { ...definition, exit_long: cond ?? null };
}

export function setExitShort(
  definition: StrategyDefinition,
  cond: Condition | null | undefined,
): StrategyDefinition {
  return { ...definition, exit_short: cond ?? null };
}

export function setFilters(
  definition: StrategyDefinition,
  filters: Condition[],
): StrategyDefinition {
  return { ...definition, filters };
}

export function setRisk(
  definition: StrategyDefinition,
  risk: RiskSpec,
): StrategyDefinition {
  return { ...definition, risk };
}

export function setCosts(
  definition: StrategyDefinition,
  costs: CostSpec,
): StrategyDefinition {
  return { ...definition, costs };
}

// --------------------------------------------------------------------------
// Parameters: sweep grid
// --------------------------------------------------------------------------

// Mirrors ParameterSpec.sweep_values() in backend/app/strategy/definition.py
// exactly, including the round-by-index trick (accumulating by i * step
// rather than repeatedly adding step, so a fractional step does not drift
// the grid off its endpoint) — so the count shown in the card is the number
// of runs a sweep will actually perform.
export function sweepValues(spec: ParameterSpec): number[] {
  if (spec.lo == null || spec.hi == null || spec.step == null) {
    return [spec.value];
  }
  const out: number[] = [];
  const n = Math.round((spec.hi - spec.lo) / spec.step);
  for (let i = 0; i <= n; i++) {
    out.push(Math.round((spec.lo + i * spec.step) * 1e10) / 1e10);
  }
  return out;
}

// "4 Werte: 3, 5, 7, 9" — what the parameter card shows inline.
export function sweepGridLabel(spec: ParameterSpec): string {
  const values = sweepValues(spec);
  if (values.length <= 1) return "1 Wert (kein Sweep)";
  const shown =
    values.length > 8
      ? [...values.slice(0, 4).map(String), "…", ...values.slice(-3).map(String)]
      : values.map(String);
  return `${values.length} Werte: ${shown.join(", ")}`;
}

export function defaultParameter(value = 1): ParameterSpec {
  return { value, lo: null, hi: null, step: null, description: null };
}

// --------------------------------------------------------------------------
// Parameters: rename
// --------------------------------------------------------------------------

export class ParameterRenameError extends Error {}

// A parameter name is referenced from anywhere a Number is accepted (const
// operands, stop/target values, breakeven/trail, indicator params) via
// {"param": name}. Renaming repoints every one of those references — the
// same choice made for indicator ids, and for the same reason: refusing
// would just push a fixup the UI already knows how to do onto the user.
export function renameParameter(
  definition: StrategyDefinition,
  oldName: string,
  rawNewName: string,
): StrategyDefinition {
  const newName = rawNewName.trim();
  if (newName === oldName) return definition;
  if (!newName) {
    throw new ParameterRenameError("Parametername darf nicht leer sein.");
  }
  if (Object.prototype.hasOwnProperty.call(definition.parameters, newName)) {
    throw new ParameterRenameError(`Parameter "${newName}" existiert bereits.`);
  }
  const spec = definition.parameters[oldName];
  if (!spec) {
    throw new ParameterRenameError(`Parameter "${oldName}" existiert nicht.`);
  }

  const parameters: Record<string, ParameterSpec> = {};
  for (const [name, s] of Object.entries(definition.parameters)) {
    parameters[name === oldName ? newName : name] = s;
  }

  const remapNumber = (n: StrategyNumber): StrategyNumber =>
    isParamRef(n) && n.param === oldName ? { param: newName } : n;

  const remapOperand = (op: Operand): Operand =>
    op.op === "const" ? { ...op, value: remapNumber(op.value) } : op;

  const remapCondition = (cond: Condition): Condition =>
    cond.node === "compare"
      ? { ...cond, left: remapOperand(cond.left), right: remapOperand(cond.right) }
      : { ...cond, terms: cond.terms.map(remapCondition) };

  const remapNullable = (
    cond: Condition | null | undefined,
  ): Condition | null | undefined => (cond ? remapCondition(cond) : cond);

  const remapIndicator = (ind: IndicatorSpec): IndicatorSpec => ({
    ...ind,
    params: Object.fromEntries(
      Object.entries(ind.params).map(([k, v]) => [k, remapNumber(v)]),
    ),
  });

  const stop = definition.risk.stop;
  const target = definition.risk.target;

  return {
    ...definition,
    parameters,
    indicators: definition.indicators.map(remapIndicator),
    entry_long: remapNullable(definition.entry_long),
    entry_short: remapNullable(definition.entry_short),
    exit_long: remapNullable(definition.exit_long),
    exit_short: remapNullable(definition.exit_short),
    filters: definition.filters.map(remapCondition),
    risk: {
      ...definition.risk,
      stop: {
        ...stop,
        value: remapNumber(stop.value),
        breakeven_at_r:
          stop.breakeven_at_r != null ? remapNumber(stop.breakeven_at_r) : stop.breakeven_at_r,
        trail_atr_multiple:
          stop.trail_atr_multiple != null
            ? remapNumber(stop.trail_atr_multiple)
            : stop.trail_atr_multiple,
      },
      target: target ? { ...target, value: remapNumber(target.value) } : target,
    },
  };
}

// --------------------------------------------------------------------------
// Indicators
// --------------------------------------------------------------------------

export function defaultIndicator(kind: IndicatorKind, id: string): IndicatorSpec {
  return { id, kind, source: "close", params: {} };
}

export class IndicatorRenameError extends Error {}

// Renaming an indicator's id repoints every rule, filter and risk reference
// that used the old id, rather than refusing the rename or leaving dangling
// references behind — an id is the author's handle for the series, not a
// load-bearing identity, and the definition would otherwise fail backend
// validation with an "unknown indicator" error the user did not directly
// cause. A rename onto an id already used by a *different* indicator is
// refused: that would silently merge two indicators into one.
export function renameIndicatorId(
  definition: StrategyDefinition,
  oldId: string,
  rawNewId: string,
): StrategyDefinition {
  const newId = rawNewId.trim();
  if (newId === oldId) return definition;
  if (!newId) {
    throw new IndicatorRenameError("Indikator-ID darf nicht leer sein.");
  }
  if (definition.indicators.some((ind) => ind.id === newId)) {
    throw new IndicatorRenameError(`Indikator-ID "${newId}" ist bereits vergeben.`);
  }

  const remapOperand = (op: Operand): Operand =>
    op.op === "indicator" && op.id === oldId ? { ...op, id: newId } : op;

  const remapCondition = (cond: Condition): Condition =>
    cond.node === "compare"
      ? { ...cond, left: remapOperand(cond.left), right: remapOperand(cond.right) }
      : { ...cond, terms: cond.terms.map(remapCondition) };

  const remapNullable = (
    cond: Condition | null | undefined,
  ): Condition | null | undefined => (cond ? remapCondition(cond) : cond);

  const stop = definition.risk.stop;
  const target = definition.risk.target;

  return {
    ...definition,
    indicators: definition.indicators.map((ind) =>
      ind.id === oldId ? { ...ind, id: newId } : ind,
    ),
    entry_long: remapNullable(definition.entry_long),
    entry_short: remapNullable(definition.entry_short),
    exit_long: remapNullable(definition.exit_long),
    exit_short: remapNullable(definition.exit_short),
    filters: definition.filters.map(remapCondition),
    risk: {
      ...definition.risk,
      stop: stop.indicator_id === oldId ? { ...stop, indicator_id: newId } : stop,
      target:
        target && target.indicator_id === oldId
          ? { ...target, indicator_id: newId }
          : target,
    },
  };
}

// --------------------------------------------------------------------------
// Condition trees: path-addressed, immutable edits.
//
// A path is the sequence of `terms` indices from the root to a node; []
// means the root itself. Everything below only ever spreads-and-replaces
// along the path, so an untouched sibling branch keeps its original object
// identity and the input tree is never mutated.
// --------------------------------------------------------------------------

export type ConditionPath = number[];

export function getNodeAtPath(root: Condition, path: ConditionPath): Condition {
  let cur = root;
  for (const index of path) {
    if (cur.node === "compare") {
      throw new Error("path runs through a comparison node");
    }
    const next = cur.terms[index];
    if (!next) throw new Error(`path index ${index} out of range`);
    cur = next;
  }
  return cur;
}

export function replaceNodeAtPath(
  root: Condition,
  path: ConditionPath,
  next: Condition,
): Condition {
  if (path.length === 0) return next;
  const [index, ...rest] = path;
  if (root.node === "compare") {
    throw new Error("path runs through a comparison node");
  }
  return {
    node: root.node,
    terms: root.terms.map((term, i) =>
      i === index ? replaceNodeAtPath(term, rest, next) : term,
    ),
  };
}

export function addTermAtPath(
  root: Condition,
  path: ConditionPath,
  term: Condition,
): Condition {
  const target = getNodeAtPath(root, path);
  if (target.node === "compare") {
    throw new Error("cannot add a term to a comparison");
  }
  return replaceNodeAtPath(root, path, {
    node: target.node,
    terms: [...target.terms, term],
  });
}

export function removeTermAtPath(
  root: Condition,
  path: ConditionPath,
  index: number,
): Condition {
  const target = getNodeAtPath(root, path);
  if (target.node === "compare") {
    throw new Error("cannot remove a term from a comparison");
  }
  return replaceNodeAtPath(root, path, {
    node: target.node,
    terms: target.terms.filter((_, i) => i !== index),
  });
}

// --------------------------------------------------------------------------
// Operands & comparisons
// --------------------------------------------------------------------------

export function defaultPriceOperand(): PriceOperand {
  return { op: "price", field: "close", offset: 0 };
}
export function defaultIndicatorOperand(id = ""): IndicatorOperand {
  return { op: "indicator", id, offset: 0 };
}
export function defaultConstOperand(): ConstOperand {
  return { op: "const", value: 0 };
}
export function defaultPositionOperand(): PositionOperand {
  return { op: "position", field: "bars_held" };
}

export function defaultOperand(kind: Operand["op"], indicatorId = ""): Operand {
  switch (kind) {
    case "price":
      return defaultPriceOperand();
    case "indicator":
      return defaultIndicatorOperand(indicatorId);
    case "const":
      return defaultConstOperand();
    case "position":
      return defaultPositionOperand();
  }
}

export function defaultComparison(): Comparison {
  return {
    node: "compare",
    left: defaultPriceOperand(),
    cmp: ">",
    right: defaultConstOperand(),
  };
}

export function defaultBoolNode(node: BoolNode["node"]): BoolNode {
  return { node, terms: [defaultComparison()] };
}

// A crossing comparator compares a bar with the one right before it, so the
// schema refuses an offset on either side of it (see CROSSING in
// definition.py). Hardcoded here for the same reason the Comparator union
// itself is hardcoded in lib/types.ts: it is a fixed pair, not something the
// vocabulary payload needs to be consulted for at the logic layer (the
// vocabulary still drives what the UI *offers*).
const CROSSING_COMPARATORS: ReadonlySet<Comparator> = new Set([
  "cross_above",
  "cross_below",
]);

export function isCrossingComparator(cmp: Comparator): boolean {
  return CROSSING_COMPARATORS.has(cmp);
}

function stripOffset(op: Operand): Operand {
  return op.op === "price" || op.op === "indicator" ? { ...op, offset: 0 } : op;
}

// Switching to a crossing comparator strips any offset on both sides, since
// the resulting comparison would otherwise be rejected by the backend
// ("'cross_above' compares a bar with the one before it and cannot take an
// offset").
export function setComparator(cmp: Comparison, next: Comparator): Comparison {
  if (!isCrossingComparator(next)) {
    return { ...cmp, cmp: next };
  }
  return {
    ...cmp,
    cmp: next,
    left: stripOffset(cmp.left),
    right: stripOffset(cmp.right),
  };
}

// --------------------------------------------------------------------------
// Risk
// --------------------------------------------------------------------------

export function defaultStop(kind: StopSpec["kind"]): StopSpec {
  return {
    kind,
    value: kind === "atr_multiple" ? 2 : 1,
    indicator_id: null,
    breakeven_at_r: null,
    trail_atr_multiple: null,
  };
}

export function defaultTarget(kind: TargetSpec["kind"]): TargetSpec {
  return { kind, value: kind === "r_multiple" ? 2 : 1, indicator_id: null };
}
