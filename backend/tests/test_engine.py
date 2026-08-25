"""The backtesting engine.

The centre of this file is not that the engine produces trades — it is that it
cannot see the future. A backtest with a lookahead defect does not crash or
look wrong; it produces a plausible, profitable number, which is the most
expensive kind of bug this repository can contain. `docs/BENCHMARK_DISCREPANCY.md`
records what that cost the last time.

So the lookahead tests are written as properties rather than examples. The
strongest of them is truncation invariance: a backtest over the first *k* bars
must produce exactly the trades that the full backtest produced within those
bars. Any dependence on a later bar — an indicator reading forward, a fill
priced from the wrong side of a decision, an exit that knew where the bar was
going — breaks that equality, whatever form it takes.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.data.candles import Candle, CandleSeries
from app.engine.backtest import EngineConfig, run_backtest
from app.engine.evaluator import build_signal_fn
from app.engine.indicators import INDICATORS, compute_specs
from app.engine.runner import bars_from_series, run_definition
from app.services.metrics import derive_win_loss
from app.strategy.definition import (
    Comparison,
    ConstOperand,
    CostSpec,
    IndicatorOperand,
    IndicatorSpec,
    PriceOperand,
    RiskSpec,
    StopSpec,
    StrategyDefinition,
    TargetSpec,
)

BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Synthetic data with a known shape
# --------------------------------------------------------------------------- #


def trending_series(n: int = 300) -> CandleSeries:
    """A continuous drifting sine. Each bar opens where the last one closed, so
    every gap in a result is one the engine created rather than the fixture."""
    candles = []
    previous_close = 100.0
    for i in range(n):
        close = 100 + i * 0.2 + 8 * math.sin(i / 9)
        open_ = previous_close
        candles.append(
            Candle(
                BASE + timedelta(hours=i),
                open_,
                max(open_, close) + 0.6,
                min(open_, close) - 0.6,
                close,
                1.0,
            )
        )
        previous_close = close
    return CandleSeries("BTC", "1h", candles)


def flat_series(prices: list[float]) -> CandleSeries:
    """Bars whose high and low are their open and close: no intrabar movement,
    so a test can say exactly which price was available when."""
    candles = []
    previous = prices[0]
    for i, price in enumerate(prices):
        candles.append(
            Candle(
                BASE + timedelta(hours=i),
                previous,
                max(previous, price),
                min(previous, price),
                price,
                1.0,
            )
        )
        previous = price
    return CandleSeries("BTC", "1h", candles)


def sma_cross(**overrides) -> StrategyDefinition:
    kwargs = dict(
        name="SMA cross",
        asset="BTC",
        timeframe="1h",
        direction="long",
        indicators=[
            IndicatorSpec(id="fast", kind="sma", params={"period": 5.0}),
            IndicatorSpec(id="slow", kind="sma", params={"period": 20.0}),
            IndicatorSpec(id="atr", kind="atr", params={"period": 14.0}),
        ],
        entry_long=Comparison(
            left=IndicatorOperand(id="fast"),
            cmp="cross_above",
            right=IndicatorOperand(id="slow"),
        ),
        exit_long=Comparison(
            left=IndicatorOperand(id="fast"),
            cmp="cross_below",
            right=IndicatorOperand(id="slow"),
        ),
        risk=RiskSpec(
            stop=StopSpec(kind="atr_multiple", value=2.0, indicator_id="atr"),
            target=TargetSpec(kind="r_multiple", value=3.0),
        ),
    )
    kwargs.update(overrides)
    return StrategyDefinition(**kwargs)


# --------------------------------------------------------------------------- #
# No lookahead
# --------------------------------------------------------------------------- #


def tamper_after(bars: dict, k: int) -> dict:
    """Bars 0..k-1 unchanged, everything from k on replaced by a violent zigzag.

    Bar ``k``'s *open* is deliberately preserved. A fill decided on bar k-1
    happens at that open, so leaving it alone means any difference the test
    sees came from a *decision* reading forward, not from an entry legitimately
    filling into different data.
    """
    out = {key: list(values) for key, values in bars.items()}
    previous = bars["close"][k - 1]
    for i in range(k, len(bars["close"])):
        close = previous * (0.93 if (i - k) % 2 == 0 else 1.11)
        open_ = bars["open"][i] if i == k else previous
        out["open"][i] = open_
        out["close"][i] = close
        out["high"][i] = max(open_, close) * 1.03
        out["low"][i] = min(open_, close) * 0.97
        previous = close
    return out


def _entry_decision_at(definition: StrategyDefinition, bars: dict, index: int) -> bool:
    """Whether the entry rule fires at ``index``, evaluated directly.

    The rule's own boolean rather than the resulting action: the action is also
    gated by filters and by whether a position is open, and those would mask a
    difference this test exists to see.
    """
    from app.engine.evaluator import evaluate_condition

    payload = definition.to_json_dict()
    indicators = compute_specs(payload["indicators"], bars)
    return evaluate_condition(payload["entry_long"], bars, indicators, index, None)


def _decisions_survive_tampering(definition: StrategyDefinition, bars: dict) -> list[int]:
    """Bars whose decision changed when everything after them was replaced.

    Sweeps the cut point across the series and checks the one decision that the
    cut exposes — the bar immediately before it. Checking a single cut point
    would test a single bar, and the odds of that bar being one where the rule
    is near its threshold are poor.
    """
    changed = []
    for k in range(40, len(bars["close"])):
        tampered = tamper_after(bars, k)
        if _entry_decision_at(definition, bars, k - 1) != _entry_decision_at(
            definition, tampered, k - 1
        ):
            changed.append(k - 1)
    return changed


def test_a_decision_at_a_bar_depends_on_no_later_bar():
    """The sharp form of the no-lookahead property.

    Replace everything from bar k onward with a completely different price path
    and the decision at bar k-1 must not move, because it was never entitled to
    see any of it. Every bar in the series gets its turn as k-1.

    Comparing decisions rather than trades is what makes this exact: a trade's
    *fill* legitimately depends on the bar after the decision, so comparing
    trades would confuse a lookahead defect with correct behaviour.
    """
    definition = sma_cross()
    bars = bars_from_series(trending_series(240))

    changed = _decisions_survive_tampering(definition, bars)
    assert not changed, (
        f"the decision at bars {changed} changed when later bars were replaced"
    )


def test_the_lookahead_property_would_catch_a_real_defect(monkeypatch):
    """Guard the guard.

    A property test that cannot fail proves nothing, so this injects the defect
    it is meant to catch — an indicator read one bar ahead — and asserts the
    check above breaks.

    This test is also the reason that check sweeps every bar and compares
    decisions rather than trades. Two more obvious formulations both pass with
    this defect present: "truncating the data does not change the trades that
    finished before the cut" never exposes the defect at all, because such a
    trade's last decision is at least two bars before the cut; and tampering at
    a single cut point exposes exactly one decision, which is usually nowhere
    near the rule's threshold.
    """
    from app.engine import evaluator

    original = evaluator._operand_value

    def peeking(operand, bars, indicators, index, position):
        if operand.get("op") == "indicator":
            index = min(index + 1, len(bars["close"]) - 1)
        return original(operand, bars, indicators, index, position)

    monkeypatch.setattr(evaluator, "_operand_value", peeking)

    definition = sma_cross()
    bars = bars_from_series(trending_series(240))

    assert _decisions_survive_tampering(definition, bars), (
        "an indicator reading one bar ahead went unnoticed"
    )


def test_truncating_the_data_does_not_change_the_trades_that_finished():
    """The end-to-end companion to the decision-level property above.

    Weaker than it looks — see ``test_the_lookahead_property_would_catch_a_real
    _defect`` for why a one-bar lookahead survives it — but it exercises the
    whole path rather than the evaluator alone, and a coarser defect (an
    indicator computed over the full series and then sliced, an exit priced
    from a later bar) shows up here.
    """
    series = trending_series(300)
    full = run_definition(sma_cross(), series)
    assert full.trades, "the fixture produced no trades to compare"

    for k in (120, 180, 240):
        partial = run_definition(
            sma_cross(), series.slice(end=BASE + timedelta(hours=k))
        )
        settled = [t.as_dict() for t in partial.trades if t.exit_reason != "end_of_data"]
        expected = [t.as_dict() for t in full.trades if t.exit_index < k]
        assert settled == expected, (
            f"trades that finished inside the first {k} bars changed when the "
            "later bars were removed"
        )


def test_an_oracle_strategy_cannot_profit_from_the_bar_it_decided_on():
    """A strategy that buys whenever the *current* bar closed up would be
    printing money if the engine filled it at that same close. Filled at the
    next open — which is what actually happens — it earns nothing special.

    The data alternates up and down bars, so "the last bar rose" predicts
    exactly nothing about the next one.
    """
    prices = [100 + (2 if i % 2 == 0 else -2) for i in range(200)]
    series = flat_series(prices)

    definition = StrategyDefinition(
        name="Buy after an up bar",
        asset="BTC",
        timeframe="1h",
        direction="long",
        indicators=[IndicatorSpec(id="atr", kind="atr", params={"period": 14.0})],
        entry_long=Comparison(
            left=PriceOperand(field="close"),
            cmp=">",
            right=PriceOperand(field="open"),
        ),
        exit_long=Comparison(
            left=PriceOperand(field="close"),
            cmp="<",
            right=PriceOperand(field="open"),
        ),
        risk=RiskSpec(stop=StopSpec(kind="percent", value=5.0)),
        costs=CostSpec(entry_fee_pct=0.0, exit_fee_pct=0.0),
    )

    result = run_definition(definition, series)
    total_r = sum(t.r_value for t in result.trades)
    assert result.trades, "the fixture should produce trades at all"
    assert total_r <= 0.001, (
        f"a strategy with no predictive content earned {total_r:+.4f}R; the engine "
        "is filling on the bar the decision was made from"
    )


def test_an_entry_fills_at_the_next_bar_open():
    """Stated as an equality rather than an inequality, because "not the close"
    would also be satisfied by filling somewhere else wrong."""
    series = trending_series(200)
    bars = bars_from_series(series)
    result = run_definition(sma_cross(costs=CostSpec(entry_fee_pct=0.0, exit_fee_pct=0.0)), series)

    assert result.trades
    for trade in result.trades:
        assert trade.entry_price == pytest.approx(bars["open"][trade.entry_index])


def test_an_indicator_at_a_bar_ignores_every_later_bar():
    series = trending_series(120)
    bars = bars_from_series(series)
    specs = [{"id": "sma", "kind": "sma", "source": "close", "params": {"period": 10}}]
    reference = compute_specs(specs, bars)["sma"]

    tampered = dict(bars)
    tampered["close"] = list(bars["close"])
    for i in range(80, 120):
        tampered["close"][i] = 10_000.0
    after = compute_specs(specs, tampered)["sma"]

    assert after[:80] == reference[:80], "an indicator read a bar it should not see"
    assert after[80:] != reference[80:], "the fixture did not actually change anything"


def test_a_negative_offset_is_refused_by_the_context():
    from app.strategy.interface import Bar, Context, LookaheadError

    bars = [Bar(BASE + timedelta(hours=i), 1.0, 2.0, 0.5, 1.5) for i in range(10)]
    ctx = Context(bars, {"sma": [1.0] * 10}, index=5, params={}, position=None)

    with pytest.raises(LookaheadError):
        ctx.bar_at(-1)
    with pytest.raises(LookaheadError):
        ctx.price("close", -2)
    with pytest.raises(LookaheadError):
        ctx.indicator("sma", -1)


def test_the_context_cannot_be_walked_past_the_current_bar():
    """There is no accessor that returns a later bar; the only index that moves
    is the engine's."""
    from app.strategy.interface import Bar, Context

    bars = [Bar(BASE + timedelta(hours=i), float(i), float(i), float(i), float(i)) for i in range(10)]
    ctx = Context(bars, {}, index=4, params={}, position=None)

    assert ctx.bar.close == 4.0
    assert ctx.history("close", 100) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert max(ctx.history("close", 10)) == 4.0


def test_an_indicator_before_the_start_reads_as_not_ready():
    """Same answer as warm-up, because it is the same situation from the other
    end — and a strategy asking for the previous bar on bar zero is ordinary."""
    from app.strategy.interface import Bar, Context

    bars = [Bar(BASE, 1.0, 2.0, 0.5, 1.5)]
    ctx = Context(bars, {"sma": [1.0]}, index=0, params={}, position=None)
    assert ctx.indicator("sma", 1) is None


# --------------------------------------------------------------------------- #
# Fills, stops and targets
# --------------------------------------------------------------------------- #


def _single_entry_config(**overrides) -> EngineConfig:
    defaults = dict(
        stop_kind="fixed_points",
        stop_value=10.0,
        target_kind="r_multiple",
        target_value=2.0,
        entry_fee_pct=0.0,
        exit_fee_pct=0.0,
    )
    defaults.update(overrides)
    return EngineConfig(**defaults)


def _enter_once():
    """Signal a long on the first bar and nothing afterwards."""
    from app.engine.evaluator import _Signal

    def signal_fn(index, position):
        return _Signal("enter_long") if index == 0 and position is None else None

    return signal_fn


def _bars(rows: list[tuple[float, float, float, float]]) -> dict:
    return {
        "ts": [(BASE + timedelta(hours=i)).isoformat() for i in range(len(rows))],
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "volume": [1.0] * len(rows),
    }


def test_the_stop_wins_when_a_bar_touches_both():
    """OHLC cannot say which came first. Taking the target would make every
    result better and some of them fictional."""
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry fills here at 100; stop 90, target 120
        (100, 125, 85, 100),    # touches both
    ])
    result = run_backtest(bars, {}, _single_entry_config(), _enter_once())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(90.0)
    assert trade.r_value == pytest.approx(-1.0)


def test_a_gap_through_the_stop_fills_at_the_open():
    """Modelling the stop price would credit the strategy with liquidity that
    was not there — the loss is larger than 1R and the result should say so."""
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry at 100, stop 90
        (80, 82, 78, 80),       # opens straight through the stop
    ])
    result = run_backtest(bars, {}, _single_entry_config(), _enter_once())

    trade = result.trades[0]
    assert trade.exit_reason == "stop_gap"
    assert trade.exit_price == pytest.approx(80.0)
    assert trade.r_value == pytest.approx(-2.0)


def test_a_gap_through_the_target_also_fills_at_the_open():
    """The rule is "you get the open", applied in both directions rather than
    only the flattering one."""
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry at 100, target 120
        (130, 132, 128, 130),
    ])
    result = run_backtest(bars, {}, _single_entry_config(), _enter_once())

    trade = result.trades[0]
    assert trade.exit_reason == "target_gap"
    assert trade.exit_price == pytest.approx(130.0)
    assert trade.r_value == pytest.approx(3.0)


def test_a_target_reached_intrabar_fills_at_the_target():
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 125, 99, 105),
    ])
    result = run_backtest(bars, {}, _single_entry_config(), _enter_once())
    assert result.trades[0].exit_reason == "target"
    assert result.trades[0].r_value == pytest.approx(2.0)


def test_max_bars_held_closes_a_position_that_will_not_exit():
    bars = _bars([(100, 101, 99, 100)] * 20)
    config = _single_entry_config(target_kind=None, max_bars_held=5)
    result = run_backtest(bars, {}, config, _enter_once())

    trade = result.trades[0]
    assert trade.exit_reason == "max_bars"
    assert trade.bars_held == 5


def test_a_position_open_at_the_end_is_closed_and_flagged():
    bars = _bars([(100, 101, 99, 100)] * 6)
    result = run_backtest(bars, {}, _single_entry_config(target_kind=None), _enter_once())

    assert result.trades[0].exit_reason == "end_of_data"
    assert any("still open at the end" in w for w in result.warnings)


def test_an_entry_whose_stop_cannot_be_computed_is_skipped_and_reported():
    """Silently not taking the trade would make a strategy look selective when
    it was only under-warmed."""
    bars = _bars([(100, 101, 99, 100)] * 5)
    config = _single_entry_config(stop_kind="atr_multiple", stop_indicator="atr")
    result = run_backtest(bars, {"atr": [None] * 5}, config, _enter_once())

    assert result.trades == []
    assert any("stop could not be computed" in w for w in result.warnings)


def test_a_stop_on_the_wrong_side_of_the_entry_is_refused():
    bars = _bars([(100, 101, 99, 100)] * 5)
    config = _single_entry_config(stop_kind="indicator", stop_indicator="level")
    result = run_backtest(bars, {"level": [150.0] * 5}, config, _enter_once())

    assert result.trades == []
    assert any("wrong side" in w for w in result.warnings)


def test_the_break_even_stop_only_moves_once_and_only_upward():
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry at 100, stop 90
        (100, 112, 100, 111),   # +1.1R, break-even at 1R moves the stop to 100
        (111, 111, 95, 96),     # would have been fine against 90; stops at 100
    ])
    config = _single_entry_config(target_kind=None, breakeven_at_r=1.0)
    result = run_backtest(bars, {}, config, _enter_once())

    trade = result.trades[0]
    assert trade.exit_price == pytest.approx(100.0)
    assert trade.r_value == pytest.approx(0.0)
    assert trade.win_loss == "draw"


def test_a_trailing_stop_tightens_and_never_loosens():
    """Two things at once: the stop follows price up, and it stays there when
    price falls back. A stop that could loosen is not a stop."""
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),   # entry 100, initial stop 90
        (100, 120, 100, 120),   # close 120 trails the stop to 120 - 2*5 = 110
        (120, 121, 105, 108),   # low 105 takes out the trailed stop at 110
    ])
    config = _single_entry_config(
        target_kind=None, trail_atr_multiple=2.0, stop_indicator="atr"
    )
    result = run_backtest(bars, {"atr": [5.0] * 4}, config, _enter_once())

    trade = result.trades[0]
    assert trade.stop_price == pytest.approx(110.0)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.r_value == pytest.approx(1.0), "the trail should bank the move"


def test_a_trailed_stop_still_obeys_the_gap_rule():
    """A bar that opens past the trailed stop fills at the open, not at the
    stop — the same rule as an untrailed one, and worth pinning because the
    trail makes the gap wider and the difference larger."""
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 120, 100, 120),   # trail to 110
        (120, 121, 119, 100),   # holds above 110 all bar
        (100, 101, 95, 96),     # opens at 100, straight through 110
    ])
    config = _single_entry_config(
        target_kind=None, trail_atr_multiple=2.0, stop_indicator="atr"
    )
    trade = run_backtest(bars, {"atr": [5.0] * 5}, config, _enter_once()).trades[0]

    assert trade.stop_price == pytest.approx(110.0)
    assert trade.exit_reason == "stop_gap"
    assert trade.exit_price == pytest.approx(100.0)


# --------------------------------------------------------------------------- #
# Costs and R
# --------------------------------------------------------------------------- #


def test_costs_are_charged_in_r_and_reduce_the_result():
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 125, 99, 105),
    ])
    free = run_backtest(bars, {}, _single_entry_config(), _enter_once()).trades[0]
    charged = run_backtest(
        bars,
        {},
        _single_entry_config(entry_fee_pct=0.000144, exit_fee_pct=0.000432),
        _enter_once(),
    ).trades[0]

    assert free.gross_r == pytest.approx(charged.gross_r)
    assert free.cost_r == 0.0
    assert charged.cost_r > 0
    assert charged.r_value == pytest.approx(charged.gross_r - charged.cost_r)
    # Fees are per unit, divided by the risk per unit: 100·0.000144 + 120·0.000432
    # over a 10-point stop.
    assert charged.cost_r == pytest.approx((100 * 0.000144 + 120 * 0.000432) / 10)


def test_slippage_moves_both_fills_against_the_trade():
    bars = _bars([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 125, 99, 105),
    ])
    config = _single_entry_config(slippage_pct=0.001)
    trade = run_backtest(bars, {}, config, _enter_once()).trades[0]

    assert trade.entry_price > 100.0, "a long should pay up to get in"
    assert trade.exit_price < trade.stop_price + 1e9  # sanity
    assert trade.r_value < 2.0, "slippage should cost, not pay"


def test_funding_accrues_with_time_held():
    bars = _bars([(100, 101, 99, 100)] * 30)
    base_config = _single_entry_config(target_kind=None, max_bars_held=24)
    without = run_backtest(bars, {}, base_config, _enter_once()).trades[0]
    with_funding = run_backtest(
        bars,
        {},
        _single_entry_config(
            target_kind=None, max_bars_held=24, funding_pct_per_day=0.0003
        ),
        _enter_once(),
    ).trades[0]

    assert with_funding.gross_r == pytest.approx(without.gross_r)
    # 24 hourly bars is one day: 100 · 0.0003 · 1 day over a 10-point stop.
    assert with_funding.cost_r == pytest.approx(100 * 0.0003 * 1.0 / 10)


def test_win_loss_agrees_with_the_importer_wherever_the_workbook_commits():
    """``metrics.py`` is verified and untouched by this phase, so the engine
    duplicates its rule rather than importing it. The duplication is only safe
    if something checks the two still agree."""
    from app.engine.backtest import _win_loss

    for r in (-2.5, -0.5, -0.100001, 0.0, 0.001, 3.0):
        assert _win_loss(r) == derive_win_loss(r), f"disagreement at R={r}"


def test_the_engine_classifies_small_losses_the_workbook_left_blank():
    """The one deliberate divergence, pinned so it cannot become accidental.

    ``derive_win_loss`` reproduces the research workbook, where -0.1 <= R < 0
    was left as an empty cell. The engine watched the trade close below its
    entry and says "loss", because carrying a spreadsheet's blank cell into
    generated results would undercount losses for every engine system.
    """
    from app.engine.backtest import _win_loss

    for r in (-0.001, -0.05, -0.1):
        assert derive_win_loss(r) is None
        assert _win_loss(r) == "loss"


# --------------------------------------------------------------------------- #
# One engine, two authoring paths
# --------------------------------------------------------------------------- #

PYTHON_SMA_CROSS = '''
class SmaCross(Strategy):
    name = "SMA cross"

    def on_bar(self, ctx):
        fast, slow = ctx.indicator("fast"), ctx.indicator("slow")
        prev_fast, prev_slow = ctx.indicator("fast", 1), ctx.indicator("slow", 1)
        if None in (fast, slow, prev_fast, prev_slow):
            return None
        if ctx.position is None:
            if prev_fast <= prev_slow and fast > slow:
                return Signal.enter_long()
        elif prev_fast >= prev_slow and fast < slow:
            return Signal.exit()
        return None
'''


@pytest.mark.sandbox
def test_the_python_path_and_the_declarative_path_agree_exactly():
    """The same rules expressed both ways must produce the same trades, to the
    last decimal. They share one engine; a difference could only come from the
    rules, and here the rules are the same."""
    series = trending_series(300)
    declarative = sma_cross()
    written = sma_cross(
        rules="python",
        python_source=PYTHON_SMA_CROSS,
        entry_long=None,
        exit_long=None,
    )

    left = run_definition(declarative, series)
    right = run_definition(written, series)

    assert left.trades, "the fixture produced no trades to compare"
    assert [t.as_dict() for t in left.trades] == [t.as_dict() for t in right.trades]


@pytest.mark.sandbox
def test_a_python_strategy_that_reaches_forward_fails_the_run():
    """Not silently, and not with a plausible number."""
    series = trending_series(60)
    written = sma_cross(
        rules="python",
        entry_long=None,
        exit_long=None,
        python_source=(
            "class Cheat(Strategy):\n"
            "    def on_bar(self, ctx):\n"
            "        ctx.indicator('fast', -1)\n"
            "        return None\n"
        ),
    )
    from app.strategy.sandbox import UserCodeError

    with pytest.raises(UserCodeError, match="LookaheadError"):
        run_definition(written, series)


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def test_every_indicator_the_schema_allows_is_implemented():
    """The schema's ``IndicatorKind`` and the engine's registry are two lists of
    the same thing; a definition that validates and then cannot be computed is
    the failure this prevents."""
    import typing

    from app.strategy.definition import IndicatorKind

    declared = set(typing.get_args(IndicatorKind))
    assert declared == set(INDICATORS)


def test_an_empty_series_produces_no_trades_rather_than_an_error():
    result = run_backtest(_bars([]), {}, _single_entry_config(), _enter_once())
    assert result.trades == []
    assert result.bars == 0


def test_parameter_overrides_reach_the_indicators():
    from app.strategy.definition import ParameterSpec, ParamRef

    series = trending_series(200)
    definition = sma_cross(
        parameters={"fast": ParameterSpec(value=5, lo=3, hi=15, step=2)},
        indicators=[
            IndicatorSpec(id="fast", kind="sma", params={"period": ParamRef(param="fast")}),
            IndicatorSpec(id="slow", kind="sma", params={"period": 20.0}),
            IndicatorSpec(id="atr", kind="atr", params={"period": 14.0}),
        ],
    )
    slow_version = run_definition(definition, series, overrides={"fast": 15})
    fast_version = run_definition(definition, series, overrides={"fast": 3})
    assert [t.as_dict() for t in slow_version.trades] != [
        t.as_dict() for t in fast_version.trades
    ]
