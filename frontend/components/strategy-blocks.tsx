"use client";

// The "Blöcke" tab — a structured editor over the same StrategyDefinition the
// JSON editor (components/strategy-editor.tsx via app/strategies/[id]/page.tsx)
// shows. Both are windows onto one object: this component never rebuilds the
// definition from scratch, it only ever reads a slice and writes it back with
// spread + replace (see lib/blocks.ts, where that logic actually lives — the
// fiddly correctness is in pure functions there, these components stay thin).

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Plus,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";

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
import { Textarea } from "@/components/ui/textarea";
import { ApiError, getStrategySchema } from "@/lib/api";
import {
  defaultBoolNode,
  defaultComparison,
  defaultOperand,
  defaultParameter,
  defaultTarget,
  getMetadata,
  isCrossingComparator,
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
} from "@/lib/blocks";
import { cn } from "@/lib/utils";
import {
  isParamRef,
  type BoolNode,
  type Comparator,
  type Comparison,
  type Condition,
  type CostSpec,
  type IndicatorKind,
  type IndicatorSpec,
  type Operand,
  type ParameterSpec,
  type PositionOperand,
  type PriceField,
  type RuleSlot,
  type RuleVocabulary,
  type StopSpec,
  type StrategyDefinition,
  type StrategyNumber,
  type TargetSpec,
} from "@/lib/types";

// --------------------------------------------------------------------------
// Shared save/validate state — owned by the parent page so the Editor and
// Blöcke tabs save through the exact same PUT /strategies/{id} call and show
// the exact same validation result.
// --------------------------------------------------------------------------

export interface DefinitionEditorShared {
  note: string;
  setNote: (note: string) => void;
  validation: { ok: boolean; errors: string[] } | null;
  saveError: string | null;
  saved: boolean;
  saving: boolean;
  validating: boolean;
  onValidate: () => void;
  onSave: () => void;
}

export interface StrategyBlocksProps {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  shared: DefinitionEditorShared;
}

// --------------------------------------------------------------------------
// German labels for fields the vocabulary describes only by their schema
// name. Values a validator error would use (comparators, operand kinds, …)
// are kept close to that wording so an error message and a form label agree.
// --------------------------------------------------------------------------

const DIRECTION_LABEL: Record<StrategyDefinition["direction"], string> = {
  long: "Long",
  short: "Short",
  both: "Long & Short",
};

const OPERAND_KIND_LABEL: Record<Operand["op"], string> = {
  price: "Preis",
  indicator: "Indikator",
  const: "Konstante",
  position: "Position",
};

const POSITION_FIELD_LABEL: Record<PositionOperand["field"], string> = {
  bars_held: "Bars gehalten",
  unrealised_r: "Unrealisiertes R",
  entry_price: "Entry-Preis",
  direction_sign: "Richtung (±1)",
};

const COMPARATOR_LABEL: Record<Comparator, string> = {
  "<": "<",
  "<=": "≤",
  ">": ">",
  ">=": "≥",
  "==": "=",
  "!=": "≠",
  cross_above: "kreuzt aufwärts",
  cross_below: "kreuzt abwärts",
};

const STOP_KIND_LABEL: Record<StopSpec["kind"], string> = {
  atr_multiple: "ATR-Vielfaches",
  percent: "Prozent",
  indicator: "Indikator",
  fixed_points: "Fixe Punkte",
};

const TARGET_KIND_LABEL: Record<TargetSpec["kind"], string> = {
  r_multiple: "R-Vielfaches",
  percent: "Prozent",
  indicator: "Indikator",
};

// --------------------------------------------------------------------------
// Vocabulary loading — cached at module scope (mirrors the Monaco loader
// pattern in strategy-editor.tsx), since the schema does not change while
// the app is running and every mount of the Blöcke tab needs it.
// --------------------------------------------------------------------------

let schemaPromise: Promise<RuleVocabulary> | null = null;

function loadSchema(): Promise<RuleVocabulary> {
  if (!schemaPromise) {
    schemaPromise = getStrategySchema().catch((err) => {
      schemaPromise = null; // allow a retry on the next mount
      throw err;
    });
  }
  return schemaPromise;
}

// --------------------------------------------------------------------------
// Small shared bits
// --------------------------------------------------------------------------

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

function BlockCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-2">
        <SectionTitle>{title}</SectionTitle>
        {action}
      </div>
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        {children}
      </div>
    </section>
  );
}

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onClick}
      className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
    >
      <Plus className="size-3.5" />
      {label}
    </Button>
  );
}

function RemoveIconButton({ onClick, title }: { onClick: () => void; title?: string }) {
  return (
    <Button
      type="button"
      size="icon-xs"
      variant="ghost"
      onClick={onClick}
      title={title}
      className="text-red-400/80 hover:bg-red-500/10 hover:text-red-300"
    >
      <Trash2 className="size-3.5" />
    </Button>
  );
}

// A number, or a toggle onto one of the declared parameters — the schema's
// {"param": name} reference, usable anywhere a plain number is.
function NumberOrParamInput({
  value,
  parameterNames,
  onChange,
  min,
}: {
  value: StrategyNumber;
  parameterNames: string[];
  onChange: (next: StrategyNumber) => void;
  min?: number;
}) {
  const isRef = isParamRef(value);
  return (
    <div className="flex items-center gap-1">
      <Select
        items={{ number: "Zahl", param: "Parameter" }}
        value={isRef ? "param" : "number"}
        onValueChange={(v) => {
          if (v === "param") onChange({ param: parameterNames[0] ?? "" });
          else onChange(typeof value === "number" ? value : (min ?? 0));
        }}
      >
        <SelectTrigger className="w-24">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="number">Zahl</SelectItem>
          <SelectItem value="param">Parameter</SelectItem>
        </SelectContent>
      </Select>
      {isRef ? (
        parameterNames.length > 0 ? (
          <Select
            items={Object.fromEntries(parameterNames.map((p) => [p, p]))}
            value={value.param}
            onValueChange={(p) => onChange({ param: p as string })}
          >
            <SelectTrigger className="w-28">
              <SelectValue placeholder="wählen…" />
            </SelectTrigger>
            <SelectContent>
              {parameterNames.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span className="text-xs text-zinc-600">keine Parameter definiert</span>
        )
      ) : (
        <Input
          type="number"
          min={min}
          value={value as number}
          onChange={(e) => onChange(Math.max(min ?? -Infinity, Number(e.target.value) || 0))}
          className="w-20 font-mono"
        />
      )}
    </div>
  );
}

// Same idea, but the field itself may be entirely absent (null) —
// breakeven_at_r / trail_atr_multiple.
function OptionalNumberOrParamInput({
  value,
  parameterNames,
  onChange,
}: {
  value: StrategyNumber | null | undefined;
  parameterNames: string[];
  onChange: (next: StrategyNumber | null) => void;
}) {
  const enabled = value != null;
  return (
    <div className="flex items-center gap-2">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked ? 0 : null)}
        className="size-4 rounded border-zinc-700 bg-zinc-900"
      />
      {enabled ? (
        <NumberOrParamInput value={value} parameterNames={parameterNames} onChange={onChange} />
      ) : (
        <span className="text-xs text-zinc-600">deaktiviert</span>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Metadaten
// --------------------------------------------------------------------------

function MetadataCard({
  definition,
  onChange,
  vocabulary,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  vocabulary: RuleVocabulary;
}) {
  const meta = getMetadata(definition);
  return (
    <BlockCard title="Metadaten">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="blk-asset">Asset</Label>
          <Input
            id="blk-asset"
            value={meta.asset}
            onChange={(e) =>
              onChange(setMetadata(definition, { asset: e.target.value.toUpperCase() }))
            }
            className="font-mono uppercase"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Timeframe</Label>
          <Select
            items={Object.fromEntries(vocabulary.timeframes.map((tf) => [tf, tf]))}
            value={meta.timeframe}
            onValueChange={(v) => onChange(setMetadata(definition, { timeframe: v as string }))}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {vocabulary.timeframes.map((tf) => (
                <SelectItem key={tf} value={tf}>
                  {tf}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Richtung</Label>
          <Select
            items={Object.fromEntries(
              vocabulary.directions.map((d) => [d, DIRECTION_LABEL[d] ?? d]),
            )}
            value={meta.direction}
            onValueChange={(v) =>
              onChange(setDirection(definition, v as StrategyDefinition["direction"]))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {vocabulary.directions.map((d) => (
                <SelectItem key={d} value={d}>
                  {DIRECTION_LABEL[d] ?? d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="blk-desc">Beschreibung</Label>
          <Textarea
            id="blk-desc"
            value={meta.description ?? ""}
            onChange={(e) =>
              onChange(setMetadata(definition, { description: e.target.value || null }))
            }
            placeholder="Optional…"
          />
        </div>
      </div>
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Parameter
// --------------------------------------------------------------------------

function ParametersCard({
  definition,
  onChange,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
}) {
  const [renameError, setRenameError] = useState<string | null>(null);
  const entries = Object.entries(definition.parameters);

  function handleRenameCommit(oldName: string, raw: string) {
    if (raw.trim() === oldName) return;
    try {
      onChange(renameParameter(definition, oldName, raw));
      setRenameError(null);
    } catch (err) {
      setRenameError(err instanceof Error ? err.message : "Umbenennen fehlgeschlagen.");
    }
  }

  function updateSpec(name: string, patch: Partial<ParameterSpec>) {
    onChange(
      setParameters(definition, {
        ...definition.parameters,
        [name]: { ...definition.parameters[name], ...patch },
      }),
    );
  }

  function removeParam(name: string) {
    const rest = { ...definition.parameters };
    delete rest[name];
    onChange(setParameters(definition, rest));
  }

  function addParam() {
    let n = 1;
    let name = "param_1";
    while (definition.parameters[name]) {
      n += 1;
      name = `param_${n}`;
    }
    onChange(setParameters(definition, { ...definition.parameters, [name]: defaultParameter() }));
  }

  return (
    <BlockCard title="Parameter" action={<AddButton label="Parameter" onClick={addParam} />}>
      {renameError ? <p className="mb-2 text-xs text-red-400">{renameError}</p> : null}
      {entries.length === 0 ? (
        <p className="text-sm text-zinc-500">Keine Parameter definiert.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {entries.map(([name, spec]) => (
            <div key={name} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Name</Label>
                  <Input
                    defaultValue={name}
                    onBlur={(e) => handleRenameCommit(name, e.target.value)}
                    className="w-36 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Wert</Label>
                  <Input
                    type="number"
                    value={spec.value}
                    onChange={(e) => updateSpec(name, { value: Number(e.target.value) || 0 })}
                    className="w-24 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Min (lo)</Label>
                  <Input
                    type="number"
                    value={spec.lo ?? ""}
                    placeholder="—"
                    onChange={(e) =>
                      updateSpec(name, {
                        lo: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                    className="w-24 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Max (hi)</Label>
                  <Input
                    type="number"
                    value={spec.hi ?? ""}
                    placeholder="—"
                    onChange={(e) =>
                      updateSpec(name, {
                        hi: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                    className="w-24 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Schritt</Label>
                  <Input
                    type="number"
                    value={spec.step ?? ""}
                    placeholder="—"
                    onChange={(e) =>
                      updateSpec(name, {
                        step: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                    className="w-24 font-mono"
                  />
                </div>
                <RemoveIconButton onClick={() => removeParam(name)} title="Parameter entfernen" />
              </div>
              <p className="mt-2 text-xs text-zinc-500">{sweepGridLabel(spec)}</p>
            </div>
          ))}
        </div>
      )}
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Indikatoren
// --------------------------------------------------------------------------

function IndicatorsCard({
  definition,
  onChange,
  vocabulary,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  vocabulary: RuleVocabulary;
}) {
  const [renameError, setRenameError] = useState<string | null>(null);
  const metaByKind = Object.fromEntries(vocabulary.indicators.map((i) => [i.kind, i]));
  const parameterNames = Object.keys(definition.parameters);

  function updateIndicator(index: number, patch: Partial<IndicatorSpec>) {
    onChange(
      setIndicators(
        definition,
        definition.indicators.map((ind, i) => (i === index ? { ...ind, ...patch } : ind)),
      ),
    );
  }

  function updateParam(index: number, paramName: string, value: StrategyNumber) {
    const ind = definition.indicators[index];
    updateIndicator(index, { params: { ...ind.params, [paramName]: value } });
  }

  function handleRenameCommit(oldId: string, raw: string) {
    if (raw.trim() === oldId) return;
    try {
      onChange(renameIndicatorId(definition, oldId, raw));
      setRenameError(null);
    } catch (err) {
      setRenameError(err instanceof Error ? err.message : "Umbenennen fehlgeschlagen.");
    }
  }

  function handleKindChange(index: number, kind: IndicatorKind) {
    const meta = metaByKind[kind];
    const params: Record<string, StrategyNumber> = {};
    for (const p of meta?.params ?? []) params[p.name] = p.default;
    updateIndicator(index, {
      kind,
      params,
      source: meta?.uses_source ? definition.indicators[index].source : "close",
    });
  }

  function removeIndicator(index: number) {
    onChange(setIndicators(definition, definition.indicators.filter((_, i) => i !== index)));
  }

  function addIndicator() {
    const firstKind: IndicatorKind = vocabulary.indicators[0]?.kind ?? "sma";
    const meta = metaByKind[firstKind];
    const existing = new Set(definition.indicators.map((i) => i.id));
    let n = 1;
    let id = "ind_1";
    while (existing.has(id)) {
      n += 1;
      id = `ind_${n}`;
    }
    const params: Record<string, StrategyNumber> = {};
    for (const p of meta?.params ?? []) params[p.name] = p.default;
    onChange(
      setIndicators(definition, [
        ...definition.indicators,
        { id, kind: firstKind, source: "close", params },
      ]),
    );
  }

  return (
    <BlockCard title="Indikatoren" action={<AddButton label="Indikator" onClick={addIndicator} />}>
      {renameError ? <p className="mb-2 text-xs text-red-400">{renameError}</p> : null}
      {definition.indicators.length === 0 ? (
        <p className="text-sm text-zinc-500">Keine Indikatoren definiert.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {definition.indicators.map((ind, i) => {
            const meta = metaByKind[ind.kind];
            return (
              <div
                key={i}
                className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
              >
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>ID</Label>
                    <Input
                      defaultValue={ind.id}
                      onBlur={(e) => handleRenameCommit(ind.id, e.target.value)}
                      className="w-32 font-mono"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Typ</Label>
                    <Select
                      items={Object.fromEntries(vocabulary.indicators.map((o) => [o.kind, o.label]))}
                      value={ind.kind}
                      onValueChange={(v) => handleKindChange(i, v as IndicatorKind)}
                    >
                      <SelectTrigger className="w-48">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {vocabulary.indicators.map((opt) => (
                          <SelectItem key={opt.kind} value={opt.kind}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {meta?.uses_source ? (
                    <div className="flex flex-col gap-1.5">
                      <Label>Quelle</Label>
                      <Select
                        items={Object.fromEntries(vocabulary.price_fields.map((f) => [f, f]))}
                        value={ind.source}
                        onValueChange={(v) => updateIndicator(i, { source: v as PriceField })}
                      >
                        <SelectTrigger className="w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {vocabulary.price_fields.map((f) => (
                            <SelectItem key={f} value={f}>
                              {f}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : null}
                  {(meta?.params ?? []).map((p) => (
                    <div key={p.name} className="flex flex-col gap-1.5">
                      <Label>{p.label}</Label>
                      <NumberOrParamInput
                        value={ind.params[p.name] ?? p.default}
                        parameterNames={parameterNames}
                        min={p.min}
                        onChange={(value) => updateParam(i, p.name, value)}
                      />
                    </div>
                  ))}
                  <RemoveIconButton
                    onClick={() => removeIndicator(i)}
                    title="Indikator entfernen"
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Bedingungsbaum (Einstieg / Ausstieg / Filter)
// --------------------------------------------------------------------------

function OffsetInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <Input
      type="number"
      min={0}
      value={value}
      onChange={(e) => onChange(Math.max(0, Math.trunc(Number(e.target.value) || 0)))}
      className="w-14 font-mono"
      title="Offset in Bars zurück (0 = aktueller Bar) — negative Offsets gibt es nicht, es gibt keinen „nächsten Bar“."
    />
  );
}

function OperandEditor({
  operand,
  onChange,
  vocabulary,
  indicatorIds,
  parameterNames,
  allowPosition,
  allowOffset,
}: {
  operand: Operand;
  onChange: (next: Operand) => void;
  vocabulary: RuleVocabulary;
  indicatorIds: string[];
  parameterNames: string[];
  allowPosition: boolean;
  allowOffset: boolean;
}) {
  const availableKinds = vocabulary.operand_kinds.filter((k) => k !== "position" || allowPosition);

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded border border-zinc-800 bg-zinc-900/60 px-1.5 py-1">
      <Select
        items={Object.fromEntries(availableKinds.map((k) => [k, OPERAND_KIND_LABEL[k] ?? k]))}
        value={operand.op}
        onValueChange={(v) => onChange(defaultOperand(v as Operand["op"], indicatorIds[0] ?? ""))}
      >
        <SelectTrigger className="w-24">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {availableKinds.map((k) => (
            <SelectItem key={k} value={k}>
              {OPERAND_KIND_LABEL[k] ?? k}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {operand.op === "price" ? (
        <>
          <Select
            items={Object.fromEntries(vocabulary.price_fields.map((f) => [f, f]))}
            value={operand.field}
            onValueChange={(v) => onChange({ ...operand, field: v as PriceField })}
          >
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {vocabulary.price_fields.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {allowOffset ? (
            <OffsetInput
              value={operand.offset}
              onChange={(offset) => onChange({ ...operand, offset })}
            />
          ) : null}
        </>
      ) : null}

      {operand.op === "indicator" ? (
        <>
          <Select
            items={Object.fromEntries(indicatorIds.map((id) => [id, id]))}
            value={operand.id}
            onValueChange={(v) => onChange({ ...operand, id: v as string })}
          >
            <SelectTrigger className="w-32">
              <SelectValue placeholder="wählen…" />
            </SelectTrigger>
            <SelectContent>
              {indicatorIds.map((id) => (
                <SelectItem key={id} value={id}>
                  {id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {allowOffset ? (
            <OffsetInput
              value={operand.offset}
              onChange={(offset) => onChange({ ...operand, offset })}
            />
          ) : null}
        </>
      ) : null}

      {operand.op === "const" ? (
        <NumberOrParamInput
          value={operand.value}
          parameterNames={parameterNames}
          onChange={(value) => onChange({ ...operand, value })}
        />
      ) : null}

      {operand.op === "position" ? (
        <Select
          items={Object.fromEntries(
            vocabulary.position_fields.map((f) => [f, POSITION_FIELD_LABEL[f] ?? f]),
          )}
          value={operand.field}
          onValueChange={(v) => onChange({ ...operand, field: v as PositionOperand["field"] })}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {vocabulary.position_fields.map((f) => (
              <SelectItem key={f} value={f}>
                {POSITION_FIELD_LABEL[f] ?? f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
    </div>
  );
}

function ComparisonRow({
  comparison,
  onChange,
  onRemove,
  vocabulary,
  indicatorIds,
  parameterNames,
  allowPosition,
}: {
  comparison: Comparison;
  onChange: (next: Condition) => void;
  onRemove: () => void;
  vocabulary: RuleVocabulary;
  indicatorIds: string[];
  parameterNames: string[];
  allowPosition: boolean;
}) {
  const allowOffset = !isCrossingComparator(comparison.cmp);

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 px-2.5 py-2">
      <OperandEditor
        operand={comparison.left}
        onChange={(left) => onChange({ ...comparison, left })}
        vocabulary={vocabulary}
        indicatorIds={indicatorIds}
        parameterNames={parameterNames}
        allowPosition={allowPosition}
        allowOffset={allowOffset}
      />
      <Select
        items={Object.fromEntries(
          vocabulary.comparators.map((c) => [c.op, COMPARATOR_LABEL[c.op] ?? c.op]),
        )}
        value={comparison.cmp}
        onValueChange={(v) => onChange(setComparator(comparison, v as Comparator))}
      >
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {vocabulary.comparators.map((c) => (
            <SelectItem key={c.op} value={c.op}>
              {COMPARATOR_LABEL[c.op] ?? c.op}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <OperandEditor
        operand={comparison.right}
        onChange={(right) => onChange({ ...comparison, right })}
        vocabulary={vocabulary}
        indicatorIds={indicatorIds}
        parameterNames={parameterNames}
        allowPosition={allowPosition}
        allowOffset={allowOffset}
      />
      <RemoveIconButton onClick={onRemove} title="Bedingung entfernen" />
    </div>
  );
}

// Recursive: renders a Comparison as a row, or a BoolNode as an indented
// group with its own nested rows/groups — the nesting is visually legible
// via the left border + indent, not a flat list pretending to be a tree.
function ConditionNode({
  condition,
  depth,
  onChange,
  onRemove,
  vocabulary,
  indicatorIds,
  parameterNames,
  allowPosition,
}: {
  condition: Condition;
  depth: number;
  onChange: (next: Condition) => void;
  onRemove: () => void;
  vocabulary: RuleVocabulary;
  indicatorIds: string[];
  parameterNames: string[];
  allowPosition: boolean;
}) {
  if (condition.node === "compare") {
    return (
      <ComparisonRow
        comparison={condition}
        onChange={onChange}
        onRemove={onRemove}
        vocabulary={vocabulary}
        indicatorIds={indicatorIds}
        parameterNames={parameterNames}
        allowPosition={allowPosition}
      />
    );
  }

  const boolMeta = vocabulary.bool_nodes.find((b) => b.node === condition.node);

  function setTerms(terms: Condition[]) {
    // An empty "all"/"any" is vacuously true/false and rejected by the
    // backend ("needs at least one term") — never leave one empty.
    if (terms.length === 0) {
      onChange({ node: condition.node, terms: [defaultComparison()] } as BoolNode);
      return;
    }
    onChange({ node: condition.node, terms } as BoolNode);
  }

  return (
    <div className="flex flex-col gap-2 border-l-2 border-zinc-800 pl-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          items={Object.fromEntries(vocabulary.bool_nodes.map((b) => [b.node, b.label]))}
          value={condition.node}
          onValueChange={(v) => {
            const node = v as BoolNode["node"];
            const terms = node === "not" ? condition.terms.slice(0, 1) : condition.terms;
            onChange({ node, terms: terms.length ? terms : [defaultComparison()] });
          }}
        >
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {vocabulary.bool_nodes.map((b) => (
              <SelectItem key={b.node} value={b.node}>
                {b.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-zinc-600">
          {boolMeta?.arity === "one" ? "genau eine Bedingung" : "verknüpft"}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {condition.node !== "not" ? (
            <>
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => setTerms([...condition.terms, defaultComparison()])}
                className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              >
                <Plus className="size-3" />
                Vergleich
              </Button>
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => setTerms([...condition.terms, defaultBoolNode("all")])}
                className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              >
                <Plus className="size-3" />
                Gruppe
              </Button>
            </>
          ) : null}
          <RemoveIconButton onClick={onRemove} title="Gruppe entfernen" />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {condition.terms.map((term, i) => (
          <ConditionNode
            key={i}
            condition={term}
            depth={depth + 1}
            onChange={(next) =>
              setTerms(condition.terms.map((t, idx) => (idx === i ? next : t)))
            }
            onRemove={() => setTerms(condition.terms.filter((_, idx) => idx !== i))}
            vocabulary={vocabulary}
            indicatorIds={indicatorIds}
            parameterNames={parameterNames}
            allowPosition={allowPosition}
          />
        ))}
      </div>
    </div>
  );
}

function ConditionTree({
  slot,
  condition,
  onChange,
  vocabulary,
  indicatorIds,
  parameterNames,
}: {
  slot: RuleSlot;
  condition: Condition | null | undefined;
  onChange: (next: Condition | null) => void;
  vocabulary: RuleVocabulary;
  indicatorIds: string[];
  parameterNames: string[];
}) {
  const meta = vocabulary.rule_slots.find((s) => s.slot === slot);
  const allowPosition = meta?.allows_position ?? false;
  const label = meta?.label ?? slot;
  const root = condition ?? null;

  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      {root ? (
        <ConditionNode
          condition={root}
          depth={0}
          onChange={onChange}
          onRemove={() => onChange(null)}
          vocabulary={vocabulary}
          indicatorIds={indicatorIds}
          parameterNames={parameterNames}
          allowPosition={allowPosition}
        />
      ) : (
        <button
          type="button"
          onClick={() => onChange(defaultComparison())}
          className="w-fit rounded-md border border-dashed border-zinc-700 px-3 py-1.5 text-xs text-zinc-500 transition-colors hover:border-zinc-600 hover:text-zinc-300"
        >
          + Bedingung hinzufügen
        </button>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Filter
// --------------------------------------------------------------------------

function FiltersCard({
  definition,
  onChange,
  vocabulary,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  vocabulary: RuleVocabulary;
}) {
  const meta = vocabulary.rule_slots.find((s) => s.slot === "filters");
  const allowPosition = meta?.allows_position ?? false;
  const indicatorIds = definition.indicators.map((i) => i.id);
  const parameterNames = Object.keys(definition.parameters);

  function addFilter() {
    onChange(setFilters(definition, [...definition.filters, defaultComparison()]));
  }

  return (
    <BlockCard title="Filter" action={<AddButton label="Filter" onClick={addFilter} />}>
      {definition.filters.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Keine Filter — alle Einstiege sind ungefiltert aktiv.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {definition.filters.map((f, i) => (
            <ConditionNode
              key={i}
              condition={f}
              depth={0}
              onChange={(next) =>
                onChange(
                  setFilters(
                    definition,
                    definition.filters.map((t, idx) => (idx === i ? next : t)),
                  ),
                )
              }
              onRemove={() =>
                onChange(
                  setFilters(
                    definition,
                    definition.filters.filter((_, idx) => idx !== i),
                  ),
                )
              }
              vocabulary={vocabulary}
              indicatorIds={indicatorIds}
              parameterNames={parameterNames}
              allowPosition={allowPosition}
            />
          ))}
        </div>
      )}
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Risiko
// --------------------------------------------------------------------------

function RiskCard({
  definition,
  onChange,
  vocabulary,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  vocabulary: RuleVocabulary;
}) {
  const risk = definition.risk;
  const indicatorIds = definition.indicators.map((i) => i.id);
  const parameterNames = Object.keys(definition.parameters);
  const stopMeta = vocabulary.stop_kinds.find((s) => s.kind === risk.stop.kind);
  const targetMeta = risk.target
    ? vocabulary.target_kinds.find((t) => t.kind === risk.target?.kind)
    : null;

  function updateStop(patch: Partial<StopSpec>) {
    onChange(setRisk(definition, { ...risk, stop: { ...risk.stop, ...patch } }));
  }

  function changeStopKind(kind: StopSpec["kind"]) {
    const needsIndicator =
      vocabulary.stop_kinds.find((s) => s.kind === kind)?.requires_indicator ?? false;
    updateStop({
      kind,
      indicator_id: needsIndicator ? (risk.stop.indicator_id ?? indicatorIds[0] ?? null) : null,
    });
  }

  function updateTarget(patch: Partial<TargetSpec>) {
    if (!risk.target) return;
    onChange(setRisk(definition, { ...risk, target: { ...risk.target, ...patch } }));
  }

  function toggleTarget(enabled: boolean) {
    onChange(
      setRisk(definition, {
        ...risk,
        target: enabled ? defaultTarget("r_multiple") : null,
      }),
    );
  }

  function changeTargetKind(kind: TargetSpec["kind"]) {
    if (!risk.target) return;
    const needsIndicator =
      vocabulary.target_kinds.find((t) => t.kind === kind)?.requires_indicator ?? false;
    updateTarget({
      kind,
      indicator_id: needsIndicator ? (risk.target.indicator_id ?? indicatorIds[0] ?? null) : null,
    });
  }

  return (
    <BlockCard title="Risiko">
      <div className="flex flex-col gap-5">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Stop
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Art</Label>
              <Select
                items={Object.fromEntries(
                  vocabulary.stop_kinds.map((s) => [s.kind, STOP_KIND_LABEL[s.kind] ?? s.kind]),
                )}
                value={risk.stop.kind}
                onValueChange={(v) => changeStopKind(v as StopSpec["kind"])}
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {vocabulary.stop_kinds.map((s) => (
                    <SelectItem key={s.kind} value={s.kind}>
                      {STOP_KIND_LABEL[s.kind] ?? s.kind}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Wert</Label>
              <NumberOrParamInput
                value={risk.stop.value}
                parameterNames={parameterNames}
                onChange={(value) => updateStop({ value })}
              />
            </div>
            {stopMeta?.requires_indicator ? (
              <div className="flex flex-col gap-1.5">
                <Label>Indikator</Label>
                <Select
                  items={Object.fromEntries(indicatorIds.map((id) => [id, id]))}
                  value={risk.stop.indicator_id ?? ""}
                  onValueChange={(v) => updateStop({ indicator_id: v })}
                >
                  <SelectTrigger className="w-36">
                    <SelectValue placeholder="wählen…" />
                  </SelectTrigger>
                  <SelectContent>
                    {indicatorIds.map((id) => (
                      <SelectItem key={id} value={id}>
                        {id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Label>Breakeven bei R</Label>
              <OptionalNumberOrParamInput
                value={risk.stop.breakeven_at_r}
                parameterNames={parameterNames}
                onChange={(value) => updateStop({ breakeven_at_r: value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Trail (ATR-Vielfaches)</Label>
              <OptionalNumberOrParamInput
                value={risk.stop.trail_atr_multiple}
                parameterNames={parameterNames}
                onChange={(value) => updateStop({ trail_atr_multiple: value })}
              />
            </div>
          </div>
        </div>

        <div className="border-t border-zinc-800 pt-4">
          <label className="mb-2 flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={risk.target != null}
              onChange={(e) => toggleTarget(e.target.checked)}
              className="size-4 rounded border-zinc-700 bg-zinc-900"
            />
            Take-Profit aktivieren
          </label>
          {risk.target ? (
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Art</Label>
                <Select
                  items={Object.fromEntries(
                    vocabulary.target_kinds.map((t) => [
                      t.kind,
                      TARGET_KIND_LABEL[t.kind] ?? t.kind,
                    ]),
                  )}
                  value={risk.target.kind}
                  onValueChange={(v) => changeTargetKind(v as TargetSpec["kind"])}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {vocabulary.target_kinds.map((t) => (
                      <SelectItem key={t.kind} value={t.kind}>
                        {TARGET_KIND_LABEL[t.kind] ?? t.kind}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Wert</Label>
                <NumberOrParamInput
                  value={risk.target.value}
                  parameterNames={parameterNames}
                  onChange={(value) => updateTarget({ value })}
                />
              </div>
              {targetMeta?.requires_indicator ? (
                <div className="flex flex-col gap-1.5">
                  <Label>Indikator</Label>
                  <Select
                    items={Object.fromEntries(indicatorIds.map((id) => [id, id]))}
                    value={risk.target.indicator_id ?? ""}
                    onValueChange={(v) => updateTarget({ indicator_id: v })}
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue placeholder="wählen…" />
                    </SelectTrigger>
                    <SelectContent>
                      {indicatorIds.map((id) => (
                        <SelectItem key={id} value={id}>
                          {id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-end gap-3 border-t border-zinc-800 pt-4">
          <div className="flex flex-col gap-1.5">
            <Label>Max. Bars gehalten</Label>
            <Input
              type="number"
              min={1}
              value={risk.max_bars_held ?? ""}
              placeholder="unbegrenzt"
              onChange={(e) =>
                onChange(
                  setRisk(definition, {
                    ...risk,
                    max_bars_held:
                      e.target.value === "" ? null : Math.max(1, Number(e.target.value) || 1),
                  }),
                )
              }
              className="w-32 font-mono"
            />
          </div>
        </div>
      </div>
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Kosten
// --------------------------------------------------------------------------

function CostsCard({
  definition,
  onChange,
  vocabulary,
}: {
  definition: StrategyDefinition;
  onChange: (next: StrategyDefinition) => void;
  vocabulary: RuleVocabulary;
}) {
  const costs = definition.costs;
  const fields: { key: keyof CostSpec; label: string }[] = [
    { key: "entry_fee_pct", label: "Entry-Fee" },
    { key: "exit_fee_pct", label: "Exit-Fee" },
    { key: "slippage_pct", label: "Slippage" },
    { key: "funding_pct_per_day", label: "Funding / Tag" },
  ];

  return (
    <BlockCard title="Kosten">
      <div className="grid gap-4 sm:grid-cols-4">
        {fields.map((f) => (
          <div key={f.key} className="flex flex-col gap-1.5">
            <Label>{f.label}</Label>
            <Input
              type="number"
              step="any"
              min={0}
              value={costs[f.key]}
              onChange={(e) =>
                onChange(
                  setCosts(definition, {
                    ...costs,
                    [f.key]: Math.max(0, Number(e.target.value) || 0),
                  }),
                )
              }
              className="font-mono"
            />
            <span className="text-[0.65rem] text-zinc-600">
              Default: {vocabulary.cost_defaults[f.key]}
            </span>
          </div>
        ))}
      </div>
    </BlockCard>
  );
}

// --------------------------------------------------------------------------
// Save footer — shared with the Editor tab's shape, so both tabs save
// through the exact same PUT and show the exact same validation result.
// --------------------------------------------------------------------------

function SaveFooter({ shared }: { shared: DefinitionEditorShared }) {
  const { note, setNote, validation, saveError, saved, saving, validating, onValidate, onSave } =
    shared;
  const blockedByValidation = validation !== null && !validation.ok;

  return (
    <div className="flex flex-col gap-4 border-t border-zinc-800 pt-4">
      {validation ? (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-sm",
            validation.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/30 bg-red-500/10 text-red-300",
          )}
        >
          <div className="flex items-center gap-2 font-medium">
            {validation.ok ? (
              <CheckCircle2 className="size-4 shrink-0" />
            ) : (
              <XCircle className="size-4 shrink-0" />
            )}
            {validation.ok ? "Definition gültig" : "Definition ungültig"}
          </div>
          {validation.errors.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1 pl-6 text-xs [list-style:disc]">
              {validation.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {saveError ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {saveError}
        </p>
      ) : null}
      {saved ? (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          Gespeichert.
        </p>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-64 flex-1 flex-col gap-1.5">
          <Label htmlFor="blk-save-note">Notiz (optional)</Label>
          <Input
            id="blk-save-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="z. B. Filter ergänzt"
            autoComplete="off"
          />
        </div>
        <Button
          variant="outline"
          onClick={() => onValidate()}
          disabled={validating || saving}
          className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
        >
          {validating ? <Loader2 className="size-4 animate-spin" /> : null}
          Validieren
        </Button>
        <Button onClick={() => onSave()} disabled={saving || validating || blockedByValidation}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Speichern (neue Version)
        </Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Main
// --------------------------------------------------------------------------

export function StrategyBlocks({ definition, onChange, shared }: StrategyBlocksProps) {
  const [vocabulary, setVocabulary] = useState<RuleVocabulary | null>(null);
  const [vocabError, setVocabError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadSchema()
      .then((v) => {
        if (active) setVocabulary(v);
      })
      .catch((err) => {
        if (!active) return;
        setVocabError(
          err instanceof ApiError
            ? err.status === 0
              ? "Backend nicht erreichbar."
              : err.message
            : "Vokabular konnte nicht geladen werden.",
        );
      });
    return () => {
      active = false;
    };
  }, []);

  // Live validation: debounce POST /strategies/validate on every structural
  // change while the designer is open, so an invalid definition is caught
  // here rather than discovered on Save.
  const { onValidate } = shared;
  useEffect(() => {
    if (definition.rules !== "declarative") return;
    const handle = setTimeout(() => {
      onValidate();
    }, 600);
    return () => clearTimeout(handle);
  }, [definition, onValidate]);

  if (definition.rules !== "declarative") {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-zinc-800 px-6 text-center text-sm text-zinc-500">
        Diese Strategie nutzt Python als Regel-Träger — die Logik lebt im
        Quelltext (Tab „Editor“). Die Block-Ansicht bildet nur deklarative
        Regelbäume ab und ist hier nicht anwendbar.
      </div>
    );
  }

  if (vocabError) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        {vocabError}
      </div>
    );
  }

  if (!vocabulary) {
    return (
      <div className="flex h-32 items-center justify-center gap-2 text-sm text-zinc-500">
        <Loader2 className="size-4 animate-spin" />
        Vokabular wird geladen…
      </div>
    );
  }

  const indicatorIds = definition.indicators.map((i) => i.id);
  const parameterNames = Object.keys(definition.parameters);
  const allowShort = definition.direction === "short" || definition.direction === "both";

  return (
    <div className="flex flex-col gap-6">
      <MetadataCard definition={definition} onChange={onChange} vocabulary={vocabulary} />
      <ParametersCard definition={definition} onChange={onChange} />
      <IndicatorsCard definition={definition} onChange={onChange} vocabulary={vocabulary} />

      <BlockCard title="Einstieg">
        <div className="flex flex-col gap-5">
          <ConditionTree
            slot="entry_long"
            condition={definition.entry_long}
            onChange={(next) => onChange(setEntryLong(definition, next))}
            vocabulary={vocabulary}
            indicatorIds={indicatorIds}
            parameterNames={parameterNames}
          />
          {allowShort ? (
            <ConditionTree
              slot="entry_short"
              condition={definition.entry_short}
              onChange={(next) => onChange(setEntryShort(definition, next))}
              vocabulary={vocabulary}
              indicatorIds={indicatorIds}
              parameterNames={parameterNames}
            />
          ) : null}
        </div>
      </BlockCard>

      <BlockCard title="Ausstieg">
        <div className="flex flex-col gap-5">
          <ConditionTree
            slot="exit_long"
            condition={definition.exit_long}
            onChange={(next) => onChange(setExitLong(definition, next))}
            vocabulary={vocabulary}
            indicatorIds={indicatorIds}
            parameterNames={parameterNames}
          />
          {allowShort ? (
            <ConditionTree
              slot="exit_short"
              condition={definition.exit_short}
              onChange={(next) => onChange(setExitShort(definition, next))}
              vocabulary={vocabulary}
              indicatorIds={indicatorIds}
              parameterNames={parameterNames}
            />
          ) : null}
        </div>
      </BlockCard>

      <FiltersCard definition={definition} onChange={onChange} vocabulary={vocabulary} />
      <RiskCard definition={definition} onChange={onChange} vocabulary={vocabulary} />
      <CostsCard definition={definition} onChange={onChange} vocabulary={vocabulary} />

      <SaveFooter shared={shared} />
    </div>
  );
}
