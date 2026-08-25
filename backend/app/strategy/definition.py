"""The Strategy Definition — the one shape a strategy has in this system.

Both authoring paths converge here. Python strategies are compiled down to a
definition; the visual block designer emits one directly; the backtesting
engine consumes nothing else. Keeping a single representation is what makes it
possible to open a hand-written strategy in the designer, and to sweep the
parameters of one that was written as code.

Design notes
------------
**Rules are data, not code.** Entry and exit conditions are a small typed
expression tree of comparisons over indicators, prices and position state. That
costs some expressiveness against arbitrary Python, and buys three things worth
more: the definition serialises to JSONB and back without a code path, the
designer can render it, and — the reason it is shaped this way — every operand
carries an explicit non-negative bar ``offset``, so *lookahead is unrepresentable*
rather than merely avoided. There is no syntax in this tree for "the next bar".

**Parameters are named and referenced.** Any number in the tree may instead be a
``{"param": "fast"}`` reference resolved against the declared ``parameters``.
Sweeping a strategy is then substitution rather than rewriting, and a swept
parameter is declared with its range in one place.

**Validation is eager.** Unknown indicator ids, negative offsets, a short entry
rule on a long-only strategy — all of it is refused when the definition is
built, not when the engine trips over it three hundred bars into a backtest.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Bumped whenever a stored definition would no longer round-trip. Definitions
#: carry the version they were written with; the loader refuses anything it was
#: not built for rather than guessing at the difference.
SCHEMA_VERSION = 1

PriceField = Literal["open", "high", "low", "close", "volume"]

#: Indicators the engine can compute. Adding one here means teaching
#: ``app.engine.indicators`` about it; the registry there is checked against
#: this list by a test, so the two cannot drift apart.
IndicatorKind = Literal[
    "sma",
    "ema",
    "rsi",
    "atr",
    "stdev",
    "highest",
    "lowest",
    "roc",
]


class StrategyDefinitionError(ValueError):
    """A definition is not well-formed, or is of a schema this build cannot read."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #


class ParameterSpec(_Model):
    """A named number a strategy is tuned by.

    ``lo``/``hi``/``step`` are optional and exist for E4 sweeps: they describe
    the range worth searching, so a sweep does not need a second description of
    the strategy living somewhere else.
    """

    value: float
    lo: float | None = None
    hi: float | None = None
    step: float | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "ParameterSpec":
        if self.lo is not None and self.hi is not None and self.lo > self.hi:
            raise ValueError(f"parameter range is inverted: lo={self.lo} > hi={self.hi}")
        if self.step is not None and self.step <= 0:
            raise ValueError(f"parameter step must be positive, got {self.step}")
        return self

    def sweep_values(self) -> list[float]:
        """The grid this parameter contributes to a sweep.

        A parameter with no declared range contributes only its current value,
        so a sweep over a partly-annotated strategy still works and simply does
        not vary the un-annotated axes.
        """
        if self.lo is None or self.hi is None or self.step is None:
            return [self.value]
        out: list[float] = []
        # Accumulate by index rather than repeatedly adding ``step``, so a
        # fractional step does not drift the grid off its endpoint.
        n = int(round((self.hi - self.lo) / self.step))
        for i in range(n + 1):
            out.append(round(self.lo + i * self.step, 10))
        return out


class ParamRef(_Model):
    """A reference to a declared parameter, usable anywhere a number is."""

    param: str


#: Any place the definition accepts a number, it also accepts a parameter
#: reference. ``resolve()`` substitutes them before the engine sees anything.
Number = Union[float, ParamRef]


# --------------------------------------------------------------------------- #
# Operands
# --------------------------------------------------------------------------- #


class PriceOperand(_Model):
    """A field of a bar. ``offset`` counts backwards: 0 is the bar being
    decided on, 1 the one before it. Negative offsets do not exist."""

    op: Literal["price"] = "price"
    field: PriceField = "close"
    offset: int = Field(default=0, ge=0)


class IndicatorOperand(_Model):
    """The value of a declared indicator, ``offset`` bars back."""

    op: Literal["indicator"] = "indicator"
    id: str
    offset: int = Field(default=0, ge=0)


class ConstOperand(_Model):
    op: Literal["const"] = "const"
    value: Number


class PositionOperand(_Model):
    """State of the open position, for exit rules.

    ``none`` when flat, which makes a comparison against it false rather than
    an error — an exit rule that mentions the position simply never fires while
    there is no position.
    """

    op: Literal["position"] = "position"
    field: Literal["bars_held", "unrealised_r", "entry_price", "direction_sign"]


Operand = Annotated[
    Union[PriceOperand, IndicatorOperand, ConstOperand, PositionOperand],
    Field(discriminator="op"),
]


# --------------------------------------------------------------------------- #
# Conditions
# --------------------------------------------------------------------------- #

Comparator = Literal["<", "<=", ">", ">=", "==", "!=", "cross_above", "cross_below"]

#: These need the previous bar as well as the current one, which is why they
#: are a comparator rather than something the author writes out by hand: the
#: engine can then guarantee the offsets involved are 0 and 1 and nothing else.
CROSSING = ("cross_above", "cross_below")


class Comparison(_Model):
    node: Literal["compare"] = "compare"
    left: Operand
    cmp: Comparator
    right: Operand


class BoolNode(_Model):
    """``all`` / ``any`` / ``not`` over sub-conditions.

    ``not`` takes exactly one term; the others take at least one. An empty
    ``all`` would be vacuously true and an empty ``any`` vacuously false, and
    both are far more likely to be an unfinished rule than an intention.
    """

    node: Literal["all", "any", "not"]
    terms: list["Condition"]

    @model_validator(mode="after")
    def _check_arity(self) -> "BoolNode":
        if self.node == "not" and len(self.terms) != 1:
            raise ValueError(f"'not' takes exactly one term, got {len(self.terms)}")
        if not self.terms:
            raise ValueError(f"'{self.node}' needs at least one term")
        return self


Condition = Annotated[Union[Comparison, BoolNode], Field(discriminator="node")]

BoolNode.model_rebuild()


# --------------------------------------------------------------------------- #
# Indicators, risk, costs
# --------------------------------------------------------------------------- #


class IndicatorSpec(_Model):
    """One precomputed series.

    ``id`` is the handle rules refer to. It is the author's name for the thing
    ("sma_fast"), not a derived one, so renaming a period does not silently
    repoint every rule that used it.
    """

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    kind: IndicatorKind
    source: PriceField = "close"
    params: dict[str, Number] = Field(default_factory=dict)


class StopSpec(_Model):
    """Where the initial stop goes. This defines 1R, so it is required — a
    strategy without a stop has no R, and every metric in this platform is
    denominated in R."""

    kind: Literal["atr_multiple", "percent", "indicator", "fixed_points"]
    #: ATR multiple, percent of entry, or absolute points, by ``kind``.
    value: Number = 1.0
    #: For ``kind="atr_multiple"`` and ``kind="indicator"``: which series.
    indicator_id: str | None = None
    #: Move the stop to break-even once this many R of open profit is reached.
    breakeven_at_r: Number | None = None
    #: Trail the stop by this ATR multiple once in profit. None disables it.
    trail_atr_multiple: Number | None = None

    @model_validator(mode="after")
    def _needs_indicator(self) -> "StopSpec":
        if self.kind in ("atr_multiple", "indicator") and not self.indicator_id:
            raise ValueError(f"stop kind '{self.kind}' requires indicator_id")
        return self


class TargetSpec(_Model):
    """Optional take-profit. ``r_multiple`` is the common case and is expressed
    in R directly, so a 2R target survives a change to the stop rule."""

    kind: Literal["r_multiple", "percent", "indicator"]
    value: Number = 2.0
    indicator_id: str | None = None

    @model_validator(mode="after")
    def _needs_indicator(self) -> "TargetSpec":
        if self.kind == "indicator" and not self.indicator_id:
            raise ValueError("target kind 'indicator' requires indicator_id")
        return self


class RiskSpec(_Model):
    stop: StopSpec
    target: TargetSpec | None = None
    #: Bars after which an open position is closed at market regardless. Guards
    #: against a strategy whose exit condition can, on some data, never fire.
    max_bars_held: int | None = Field(default=None, ge=1)
    #: One position at a time is the only mode the engine implements; the field
    #: exists so a definition that assumes otherwise is refused rather than
    #: silently mis-executed.
    max_concurrent_positions: Literal[1] = 1


class CostSpec(_Model):
    """Costs applied to every trade, in the same terms as the rest of the
    platform. Defaults are the verified Hyperliquid taker figures already used
    by the live-trading module (entry 0.0144 %, exit 0.0432 %)."""

    entry_fee_pct: float = Field(default=0.000144, ge=0)
    exit_fee_pct: float = Field(default=0.000432, ge=0)
    #: Applied against the fill in the adverse direction, both on entry and exit.
    slippage_pct: float = Field(default=0.0, ge=0)
    #: Charged pro rata over the bars a position is held.
    funding_pct_per_day: float = Field(default=0.0, ge=0)


# --------------------------------------------------------------------------- #
# The definition
# --------------------------------------------------------------------------- #


class StrategyDefinition(_Model):
    """Everything the engine needs, and nothing about how it was authored."""

    schema_version: int = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None

    asset: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=16)
    direction: Literal["long", "short", "both"] = "long"

    parameters: dict[str, ParameterSpec] = Field(default_factory=dict)
    indicators: list[IndicatorSpec] = Field(default_factory=list)

    entry_long: Condition | None = None
    entry_short: Condition | None = None
    exit_long: Condition | None = None
    exit_short: Condition | None = None
    #: Conditions that must all hold for any entry to be taken. Kept separate
    #: from the entry rules so a regime filter can be toggled or swept without
    #: touching the signal itself.
    filters: list[Condition] = Field(default_factory=list)

    risk: RiskSpec
    costs: CostSpec = Field(default_factory=CostSpec)

    # -- validation -------------------------------------------------------- #

    @model_validator(mode="after")
    def _validate(self) -> "StrategyDefinition":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"definition is schema_version {self.schema_version}, this build "
                f"reads {SCHEMA_VERSION}"
            )

        ids = [ind.id for ind in self.indicators]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate indicator ids: {sorted(duplicates)}")
        known = set(ids)

        for cond, label in self._conditions():
            _check_condition_refs(cond, known, label)

        for field_name in ("stop", "target"):
            spec = getattr(self.risk, field_name)
            if spec is not None and spec.indicator_id and spec.indicator_id not in known:
                raise ValueError(
                    f"risk.{field_name} references unknown indicator "
                    f"{spec.indicator_id!r}; declared: {sorted(known)}"
                )

        if self.direction == "long" and self.entry_short is not None:
            raise ValueError("direction is 'long' but entry_short is set")
        if self.direction == "short" and self.entry_long is not None:
            raise ValueError("direction is 'short' but entry_long is set")
        if self.direction in ("long", "both") and self.entry_long is None:
            raise ValueError(f"direction is '{self.direction}' but entry_long is unset")
        if self.direction in ("short", "both") and self.entry_short is None:
            raise ValueError(f"direction is '{self.direction}' but entry_short is unset")

        for ref in self._param_refs():
            if ref not in self.parameters:
                raise ValueError(
                    f"rule references undeclared parameter {ref!r}; declared: "
                    f"{sorted(self.parameters)}"
                )

        return self

    def _conditions(self) -> list[tuple[Any, str]]:
        out: list[tuple[Any, str]] = []
        for name in ("entry_long", "entry_short", "exit_long", "exit_short"):
            cond = getattr(self, name)
            if cond is not None:
                out.append((cond, name))
        out.extend((c, f"filters[{i}]") for i, c in enumerate(self.filters))
        return out

    def _param_refs(self) -> set[str]:
        found: set[str] = set()

        def walk(obj: Any) -> None:
            if isinstance(obj, ParamRef):
                found.add(obj.param)
            elif isinstance(obj, BaseModel):
                for value in obj.__dict__.values():
                    walk(value)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    walk(item)
            elif isinstance(obj, dict):
                for item in obj.values():
                    walk(item)

        walk(self)
        return found

    # -- parameter resolution ---------------------------------------------- #

    def resolve(self, overrides: dict[str, float] | None = None) -> "StrategyDefinition":
        """Return an equivalent definition with every ``ParamRef`` substituted.

        This is what a sweep varies and what the engine actually runs, so the
        engine never has to know parameters exist. ``overrides`` sets parameter
        values for this resolution only; the declared values are the default.
        """
        values = {name: spec.value for name, spec in self.parameters.items()}
        unknown = set(overrides or {}) - set(values)
        if unknown:
            raise StrategyDefinitionError(
                f"cannot override undeclared parameters {sorted(unknown)}; "
                f"declared: {sorted(values)}"
            )
        values.update(overrides or {})

        def substitute(obj: Any) -> Any:
            if isinstance(obj, ParamRef):
                return values[obj.param]
            if isinstance(obj, BaseModel):
                return {k: substitute(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [substitute(i) for i in obj]
            if isinstance(obj, tuple):
                return tuple(substitute(i) for i in obj)
            if isinstance(obj, dict):
                return {k: substitute(v) for k, v in obj.items()}
            return obj

        data = substitute(self)
        # The substituted values become the declared ones, so a resolved
        # definition is self-describing: what ran is what it says it ran.
        data["parameters"] = {
            name: {**self.parameters[name].model_dump(), "value": values[name]}
            for name in values
        }
        return StrategyDefinition.model_validate(data)

    @property
    def is_resolved(self) -> bool:
        return not self._param_refs()

    # -- serialisation ------------------------------------------------------ #

    def to_json_dict(self) -> dict[str, Any]:
        """JSON-safe dict for JSONB storage and for the API.

        ``exclude_none`` is deliberately *not* used: an explicit null is part of
        the shape the designer reads, and dropping it would make an absent field
        and a cleared one indistinguishable on the way back in.
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "StrategyDefinition":
        """Load a stored definition, refusing one this build cannot read."""
        if not isinstance(data, dict):
            raise StrategyDefinitionError(
                f"expected a definition object, got {type(data).__name__}"
            )
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise StrategyDefinitionError(
                f"stored definition is schema_version {version!r}; this build "
                f"reads {SCHEMA_VERSION}. Migrate it rather than loading it."
            )
        try:
            return cls.model_validate(data)
        except ValueError as exc:
            raise StrategyDefinitionError(str(exc)) from exc


def _check_condition_refs(cond: Any, known: set[str], label: str) -> None:
    """Walk a condition tree, refusing references to undeclared indicators."""
    if isinstance(cond, BoolNode):
        for term in cond.terms:
            _check_condition_refs(term, known, label)
        return
    if isinstance(cond, Comparison):
        for side, operand in (("left", cond.left), ("right", cond.right)):
            if isinstance(operand, IndicatorOperand) and operand.id not in known:
                raise ValueError(
                    f"{label}.{side} references unknown indicator {operand.id!r}; "
                    f"declared: {sorted(known)}"
                )
        if cond.cmp in CROSSING:
            for side, operand in (("left", cond.left), ("right", cond.right)):
                offset = getattr(operand, "offset", 0)
                if offset:
                    raise ValueError(
                        f"{label}.{side}: '{cond.cmp}' compares a bar with the one "
                        f"before it and cannot take an offset (got {offset})"
                    )
