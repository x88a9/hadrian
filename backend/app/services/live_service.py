"""Business logic for live trades (Phase 7).

DB-aware (takes a Session) but keeps the pure numeric core in ``risk_calc.py``.
Covers: current asset-settings resolution (versioned), the fee snapshot taken at
ticket creation, stage transitions, the close computation (R / win-loss /
deviation / duration / balance fortschreibung) and the live-only aggregation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AccountBalance, AssetSetting, LiveTrade, Venue
from app.services.risk_calc import (
    RiskInputs,
    RiskResult,
    compute_risk,
    deviation_pct,
)

# Break-even-Schwelle (Brief Teil D): |R| < 0.1 -> break-even.
BREAK_EVEN_ABS_R = 0.1

# Below this amount a balance difference counts as zero, and no ledger
# Eintrag) — verhindert Rausch-Zeilen aus Float-Rundung.
BALANCE_EPS = 1e-9


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Asset-Settings (versioniert) + Kontostand
# --------------------------------------------------------------------------- #
def default_venue(db: Session) -> Venue | None:
    return db.execute(select(Venue).order_by(Venue.id)).scalars().first()


def resolve_asset_setting(
    db: Session,
    venue_id: int | None = None,
    asset: str | None = None,
    at: datetime | None = None,
) -> AssetSetting | None:
    """The settings version in force for (venue, asset) at ``at`` (default now).

    Picks the greatest ``valid_from`` <= ``at``. Falls back from a concrete
    ``asset`` to the venue's ``DEFAULT`` asset, and from no venue to the first
    (seeded) venue.
    """
    at = at or now_utc()
    if venue_id is None:
        venue = default_venue(db)
        if venue is None:
            return None
        venue_id = venue.id

    def _pick(asset_name: str) -> AssetSetting | None:
        return (
            db.execute(
                select(AssetSetting)
                .where(
                    AssetSetting.venue_id == venue_id,
                    AssetSetting.asset == asset_name,
                    AssetSetting.valid_from <= at,
                )
                .order_by(AssetSetting.valid_from.desc(), AssetSetting.id.desc())
            )
            .scalars()
            .first()
        )

    if asset:
        found = _pick(asset)
        if found is not None:
            return found
    return _pick("DEFAULT")


def is_fallback_setting(setting: AssetSetting | None, asset: str | None) -> bool:
    """True when a concrete asset was requested but only DEFAULT was found.

    Then the lot size is NOT the asset's real one — the caller must warn loudly
    instead of silently sizing with another asset's granularity.
    """
    if setting is None:
        return bool(asset)
    return bool(asset) and setting.asset != asset


def current_balance_row(db: Session) -> AccountBalance | None:
    return (
        db.execute(
            select(AccountBalance).order_by(
                AccountBalance.as_of.desc(), AccountBalance.id.desc()
            )
        )
        .scalars()
        .first()
    )


def current_balance(db: Session) -> float:
    row = current_balance_row(db)
    return float(row.balance) if row is not None else 0.0


def append_balance(
    db: Session,
    *,
    balance: float,
    change_type: str,
    delta: float | None = None,
    live_trade_id: int | None = None,
    note: str | None = None,
    as_of: datetime | None = None,
) -> AccountBalance:
    row = AccountBalance(
        balance=balance,
        delta=delta,
        change_type=change_type,
        live_trade_id=live_trade_id,
        note=note,
        as_of=as_of or now_utc(),
    )
    db.add(row)
    return row


def trade_balance_delta(db: Session, live_trade_id: int) -> float:
    """Netto-Beitrag EINES Trades zum Kontostand (Summe seiner Ledger-Deltas).

    The basis of every reversal: rather than deleting rows (the ledger is
    append-only und damit revisionssicher) wird gefragt, wie viel dieser Trade
    dem Konto bisher gutgeschrieben/abgezogen hat.
    """
    db.flush()
    total = db.execute(
        select(func.sum(AccountBalance.delta)).where(
            AccountBalance.live_trade_id == live_trade_id
        )
    ).scalar()
    return float(total or 0.0)


def adjust_trade_balance(
    db: Session,
    trade: LiveTrade,
    *,
    target_delta: float,
    change_type: str,
    note: str | None = None,
    as_of: datetime | None = None,
) -> AccountBalance | None:
    """Extend the ledger so the trade's net contribution equals ``target_delta``.

    Appends exactly one compensating row carrying the difference (append-only,
    nothing is rewritten). Returns that row, or ``None`` if everything already
    stimmt.
    """
    diff = target_delta - trade_balance_delta(db, trade.id)
    if abs(diff) < BALANCE_EPS:
        return None
    return append_balance(
        db,
        balance=current_balance(db) + diff,
        change_type=change_type,
        delta=diff,
        live_trade_id=trade.id,
        note=note,
        as_of=as_of,
    )


def reverse_trade_balance(
    db: Session,
    trade: LiveTrade,
    *,
    change_type: str = "trade_delete",
    note: str | None = None,
    as_of: datetime | None = None,
) -> AccountBalance | None:
    """Kompletten Kontostand-Beitrag eines Trades neutralisieren (Ziel-Delta 0).

    Wichtig: der FK ``account_balance.live_trade_id`` ist ON DELETE SET NULL —
    deleting the trade afterwards strips the compensating row of its reference.
    The trade ID therefore ALWAYS belongs in the ``note`` text.
    """
    return adjust_trade_balance(
        db,
        trade,
        target_delta=0.0,
        change_type=change_type,
        note=note,
        as_of=as_of,
    )


# --------------------------------------------------------------------------- #
# Risk-Rechner-Anbindung
# --------------------------------------------------------------------------- #
def inputs_from_setting(
    setting: AssetSetting | None,
    *,
    entry_price: float,
    stop_price: float,
    desired_risk_usd: float,
    portfolio_size: float,
    risk_modifier: float = 1.0,
) -> RiskInputs:
    """Assemble ``RiskInputs`` from an asset-settings row (or safe defaults)."""
    if setting is not None:
        entry_fee = setting.entry_fee_pct
        exit_fee = setting.exit_fee_pct
        min_size = setting.min_position_size
        buffer = setting.leverage_buffer
        up = setting.upside_deviation_allowed_pct
        down = setting.downside_deviation_allowed_pct
        max_lev = setting.max_leverage
        lev_step = setting.leverage_step if setting.leverage_step else 1.0
        min_order = setting.min_order_value_usd
    else:
        entry_fee, exit_fee, min_size = 0.000144, 0.000432, 0.00001
        buffer, up, down = 0.1, 0.05, 0.05
        max_lev, lev_step, min_order = None, 1.0, None
    return RiskInputs(
        entry_price=entry_price,
        stop_price=stop_price,
        desired_risk_usd=desired_risk_usd,
        portfolio_size=portfolio_size,
        entry_fee_pct=entry_fee,
        exit_fee_pct=exit_fee,
        min_position_size=min_size,
        leverage_buffer=buffer,
        upside_deviation_allowed_pct=up,
        downside_deviation_allowed_pct=down,
        risk_modifier=risk_modifier,
        max_leverage=max_lev,
        leverage_step=lev_step,
        min_order_value_usd=min_order,
    )


def snapshot_settings_onto(
    trade: LiveTrade,
    inp: RiskInputs,
    setting: AssetSetting | None,
) -> None:
    """Freeze the fee/size values used onto the trade (isolation requirement).

    After this, a later global fee change can never alter this trade — it always
    computes with the snapshot.
    """
    trade.asset_setting_id = setting.id if setting is not None else None
    trade.portfolio_size_at_creation = inp.portfolio_size
    trade.snap_entry_fee_pct = inp.entry_fee_pct
    trade.snap_exit_fee_pct = inp.exit_fee_pct
    trade.snap_min_position_size = inp.min_position_size
    trade.snap_leverage_buffer = inp.leverage_buffer
    trade.snap_upside_deviation_allowed_pct = inp.upside_deviation_allowed_pct
    trade.snap_downside_deviation_allowed_pct = inp.downside_deviation_allowed_pct
    trade.snap_max_leverage = inp.max_leverage
    trade.snap_leverage_step = inp.leverage_step
    trade.snap_min_order_value_usd = inp.min_order_value_usd


def inputs_from_snapshot(
    trade: LiveTrade, *, entry_price: float, stop_price: float
) -> RiskInputs:
    """Rebuild ``RiskInputs`` from a trade's frozen snapshot (for recompute).

    ``trade.risk_usd`` already holds the **effective** risk (tier × modifier), so
    ``risk_modifier`` is 1.0 here to avoid applying the modifier twice.
    """
    return RiskInputs(
        entry_price=entry_price,
        stop_price=stop_price,
        desired_risk_usd=trade.risk_usd or 0.0,
        portfolio_size=trade.portfolio_size_at_creation or 0.0,
        entry_fee_pct=trade.snap_entry_fee_pct if trade.snap_entry_fee_pct is not None else 0.000144,
        exit_fee_pct=trade.snap_exit_fee_pct if trade.snap_exit_fee_pct is not None else 0.000432,
        min_position_size=trade.snap_min_position_size or 0.00001,
        leverage_buffer=trade.snap_leverage_buffer if trade.snap_leverage_buffer is not None else 0.1,
        upside_deviation_allowed_pct=trade.snap_upside_deviation_allowed_pct
        if trade.snap_upside_deviation_allowed_pct is not None
        else 0.05,
        downside_deviation_allowed_pct=trade.snap_downside_deviation_allowed_pct
        if trade.snap_downside_deviation_allowed_pct is not None
        else 0.05,
        risk_modifier=1.0,
        max_leverage=trade.snap_max_leverage,
        leverage_step=trade.snap_leverage_step if trade.snap_leverage_step else 1.0,
        min_order_value_usd=trade.snap_min_order_value_usd,
    )


def apply_risk_result(trade: LiveTrade, result: RiskResult) -> None:
    trade.direction = result.direction
    trade.position_size_coins = result.adjusted_pos_size
    trade.position_size_notional = result.adjusted_notional
    trade.leverage = result.leverage
    trade.implicit_leverage = result.implicit_leverage
    trade.exchange_leverage = result.exchange_leverage
    trade.expected_loss = result.adjusted_exp_loss


def snapshot_from_setting(
    trade: LiveTrade, setting: AssetSetting | None, portfolio_size: float
) -> None:
    """Freeze fee/size values from a settings row (used at ticket creation)."""
    inp = inputs_from_setting(
        setting,
        entry_price=0.0,
        stop_price=0.0,
        desired_risk_usd=0.0,
        portfolio_size=portfolio_size,
    )
    snapshot_settings_onto(trade, inp, setting)


def store_risk(
    db: Session,
    trade: LiveTrade,
    *,
    planned_entry: float | None = None,
    planned_stop: float | None = None,
    desired_risk_usd: float | None = None,
    risk_pct: float | None = None,
    risk_modifier: float | None = None,
    portfolio_size: float | None = None,
) -> RiskResult:
    """Run the risk stage: size the position from the snapshot and store results.

    ``risk_usd`` stores the **effective** risk (tier × modifier) — the 1R unit.
    Raises ``ValueError`` if inputs are insufficient.
    """
    if planned_entry is not None:
        trade.planned_entry = planned_entry
    if planned_stop is not None:
        trade.planned_stop = planned_stop
    if trade.planned_entry is None or trade.planned_stop is None:
        raise ValueError("planned_entry and planned_stop are required")

    portfolio = (
        portfolio_size
        if portfolio_size is not None
        else (trade.portfolio_size_at_creation or current_balance(db))
    )
    if portfolio_size is not None:
        trade.portfolio_size_at_creation = portfolio_size
    elif trade.portfolio_size_at_creation is None:
        trade.portfolio_size_at_creation = portfolio

    modifier = (
        risk_modifier
        if risk_modifier is not None
        else (trade.risk_modifier if trade.risk_modifier is not None else 1.0)
    )

    if desired_risk_usd is not None:
        effective = desired_risk_usd * modifier
    elif risk_pct is not None:
        effective = portfolio * risk_pct / 100.0 * modifier
    elif trade.risk_usd is not None:
        effective = trade.risk_usd  # already effective (recompute, unchanged risk)
    else:
        raise ValueError("desired_risk_usd or risk_pct is required for the first risk calc")

    trade.risk_usd = effective
    trade.risk_modifier = modifier
    trade.risk_pct = (effective / portfolio * 100.0) if portfolio else None

    inp = inputs_from_snapshot(
        trade, entry_price=trade.planned_entry, stop_price=trade.planned_stop
    )
    result = compute_risk(inp)
    apply_risk_result(trade, result)
    return result


# --------------------------------------------------------------------------- #
# Abgeleitete Kennzahlen
# --------------------------------------------------------------------------- #
def classify_win_loss(r: float | None) -> str | None:
    if r is None:
        return None
    if abs(r) < BREAK_EVEN_ABS_R:
        return "break_even"
    return "win" if r > 0 else "loss"


def _gross_pnl(direction: str, coins: float, entry: float, exit_price: float) -> float:
    if direction == "short":
        return coins * (entry - exit_price)
    return coins * (exit_price - entry)


def _est_fees(coins: float, entry: float, exit_price: float, snap_entry_fee: float, snap_exit_fee: float) -> float:
    return coins * entry * snap_entry_fee + coins * exit_price * snap_exit_fee


def compute_close(
    trade: LiveTrade,
    *,
    exit_price: float | None,
    fees_paid: float | None = None,
    funding_paid: float | None = None,
    realized_override: float | None = None,
) -> dict:
    """Pure close calculation: no database access, no side effects.

    The single source of truth for PnL/R/win-loss/deviation/slippage, used both
    when closing (``close_live_trade``) and when correcting a result afterwards
    (``recompute_close``), damit beide Wege garantiert identisch rechnen.

    ``fees_paid=None`` means "estimate from the snapshot"; ``realized_override``
    lets an explicitly reported net result (the exchange statement) take
    Preisrechnung.
    """
    entry = trade.actual_entry if trade.actual_entry is not None else trade.planned_entry
    direction = trade.direction or "long"
    coins = trade.position_size_coins or 0.0
    snap_ef = trade.snap_entry_fee_pct if trade.snap_entry_fee_pct is not None else 0.000144
    snap_xf = trade.snap_exit_fee_pct if trade.snap_exit_fee_pct is not None else 0.000432

    if fees_paid is None and entry is not None and exit_price is not None:
        fees_paid = _est_fees(coins, entry, exit_price, snap_ef, snap_xf)
    fees_paid = fees_paid or 0.0
    funding_paid = funding_paid or 0.0

    if realized_override is not None:
        # The net result is supplied externally; fees/funding are informational.
        realized = realized_override
    elif entry is not None and exit_price is not None:
        realized = (
            _gross_pnl(direction, coins, entry, exit_price) - fees_paid - funding_paid
        )
    else:
        realized = 0.0 - fees_paid - funding_paid

    r_value = realized / trade.risk_usd if trade.risk_usd else None

    # Expected result under the planned execution (slippage + fee deviation).
    # Not computable without an exit price (closing via explicit PnL) -> None.
    planned_entry = trade.planned_entry
    if planned_entry is not None and exit_price is not None:
        expected_gross = _gross_pnl(direction, coins, planned_entry, exit_price)
        expected_fees = _est_fees(coins, planned_entry, exit_price, snap_ef, snap_xf)
        expected_pnl = expected_gross - expected_fees - funding_paid
        dev = deviation_pct(realized, expected_pnl)
    else:
        dev = None

    slippage = None
    if trade.actual_entry is not None and planned_entry is not None:
        slippage = trade.actual_entry - planned_entry

    return {
        "fees_paid": fees_paid,
        "funding_paid": funding_paid,
        "realized_pnl_usd": realized,
        "r_value": r_value,
        "win_loss": classify_win_loss(r_value),
        "deviation_pct": dev,
        "slippage": slippage,
    }


def apply_close_result(
    trade: LiveTrade, result: dict, *, exit_price: float | None
) -> None:
    """Write the computed result onto the trade (no stage/timestamp/ledger)."""
    if exit_price is not None:
        trade.exit_price = exit_price
    trade.fees_paid = result["fees_paid"]
    trade.funding_paid = result["funding_paid"]
    trade.slippage = result["slippage"]
    trade.realized_pnl_usd = result["realized_pnl_usd"]
    trade.r_value = result["r_value"]
    trade.win_loss = result["win_loss"]
    trade.deviation_pct = result["deviation_pct"]


def set_duration(trade: LiveTrade, closed_at: datetime) -> None:
    start = trade.entry_filled_at or trade.opened_at or trade.created_at
    if start is None:
        return
    # start may be naive (server_default) — normalise to aware for the diff.
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    trade.duration_seconds = (closed_at - start).total_seconds()


def close_live_trade(
    db: Session,
    trade: LiveTrade,
    *,
    exit_price: float | None,
    actual_entry: float | None = None,
    actual_stop: float | None = None,
    fees_paid: float | None = None,
    funding_paid: float | None = None,
    realized_pnl_usd: float | None = None,
    rules_followed: bool | None = None,
    closed_at: datetime | None = None,
) -> AccountBalance:
    """Close a trade: compute PnL/R/win-loss/deviation/duration + write balance.

    Returns the appended ``AccountBalance`` row. Fees default to the snapshot
    estimate when not supplied; funding defaults to 0. R uses ``risk_usd`` (the
    intended 1R) as denominator and is net of fees/funding. With
    ``realized_pnl_usd`` the net result is taken as given (exchange statement)
    and overrides the price-based math.
    """
    ts = closed_at or now_utc()
    if actual_entry is not None:
        trade.actual_entry = actual_entry
    if actual_stop is not None:
        trade.actual_stop = actual_stop
    if rules_followed is not None:
        trade.rules_followed = rules_followed

    result = compute_close(
        trade,
        exit_price=exit_price,
        fees_paid=fees_paid,
        funding_paid=funding_paid,
        realized_override=realized_pnl_usd,
    )
    apply_close_result(trade, result, exit_price=exit_price)
    trade.closed_at = ts
    trade.stage = "closed"
    set_duration(trade, ts)

    realized = result["realized_pnl_usd"]
    new_balance = current_balance(db) + realized
    trade.balance_after = new_balance
    row = append_balance(
        db,
        balance=new_balance,
        change_type="trade_close",
        delta=realized,
        live_trade_id=trade.id,
        note=None,
        as_of=ts,
    )
    return row


def recompute_close(
    db: Session,
    trade: LiveTrade,
    *,
    realized_override: float | None = None,
    reestimate_fees: bool = False,
    note: str | None = None,
) -> AccountBalance | None:
    """Ein bereits geschlossener Trade wurde korrigiert -> alles neu ableiten.

    Uses the same function as closing and reconciles the account balance
    per Ausgleichszeile aus (Differenz zum bisherigen Netto-Beitrag), damit ein
    korrigiertes Ergebnis nie doppelt im Saldo landet.

    ``reestimate_fees``: re-estimate fees from the snapshot, for when the exit
    price changed and no real fees were supplied.
    """
    override = realized_override
    if override is None and trade.exit_price is None:
        # Closed via explicit PnL: with no exit price the reported figure remains
        # Netto-Ergebnis die Wahrheit.
        override = trade.realized_pnl_usd

    result = compute_close(
        trade,
        exit_price=trade.exit_price,
        fees_paid=None if reestimate_fees else trade.fees_paid,
        funding_paid=trade.funding_paid,
        realized_override=override,
    )
    apply_close_result(trade, result, exit_price=trade.exit_price)

    row = adjust_trade_balance(
        db,
        trade,
        target_delta=result["realized_pnl_usd"],
        change_type="trade_correction",
        note=note,
    )
    if row is not None:
        base = trade.balance_after
        # Carry "balance after this trade" forward; with no prior value it is the
    # new balance.
        trade.balance_after = (
            base + (row.delta or 0.0) if base is not None else row.balance
        )
    return row


# --------------------------------------------------------------------------- #
# Live-Aggregation (ohne Backtest-Rauschen)
# --------------------------------------------------------------------------- #
OPEN_STAGES = ("order_placed", "entry_filled", "running")


def live_stats(db: Session, system_id: int | None = None) -> dict:
    """Aggregate over live trades only. Cancelled tickets are excluded.

    Optionally scoped to one system (for the system-detail live section)."""
    stmt = select(LiveTrade).where(LiveTrade.stage != "cancelled")
    if system_id is not None:
        stmt = stmt.where(LiveTrade.system_id == system_id)
    trades = db.execute(stmt).scalars().all()
    closed = [t for t in trades if t.stage == "closed"]
    open_trades = [t for t in trades if t.stage in OPEN_STAGES]

    pnl = sum((t.realized_pnl_usd or 0.0) for t in closed)
    total_r = sum((t.r_value or 0.0) for t in closed if t.r_value is not None)
    wins = sum(1 for t in closed if t.win_loss == "win")
    losses = sum(1 for t in closed if t.win_loss == "loss")
    decided = wins + losses
    win_rate = (wins / decided) if decided else None
    devs = [t.deviation_pct for t in closed if t.deviation_pct is not None]
    avg_dev = (sum(devs) / len(devs)) if devs else None

    return {
        "closed_count": len(closed),
        "open_count": len(open_trades),
        "total_pnl_usd": pnl,
        "total_r": total_r,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_deviation_pct": avg_dev,
        "current_balance": current_balance(db),
    }
