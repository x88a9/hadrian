"""Unit tests for the DB-free CSV trade parser (Phase 2, T3 / D5)."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime

import pytest

from app.importers.csv_trades import parse_csv


def _csv(*rows: str) -> bytes:
    return "\n".join(rows).encode("utf-8")


def test_full_d5_mapping():
    data = _csv(
        "entry_time,exit_time,direction,entry_price,sl_price,exit_price,"
        "tp_price,exit_reason,gross_r,net_r,timeframe",
        "2024-03-01 12:30:00,2024-03-01 14:00:00,long,100.5,98.0,105.0,"
        "110.0,tp_hit,2.5,2.1,M15",
    )
    trades, skipped = parse_csv(data)
    assert skipped == 0
    assert len(trades) == 1
    t = trades[0]
    assert t.trade_datetime == datetime(2024, 3, 1, 12, 30, 0)
    assert t.direction == "long"
    assert t.entry == 100.5
    assert t.sl == 98.0
    assert t.exit == 105.0
    assert t.r_value == 2.1  # net_r, not gross_r
    assert t.timeframe == "M15"
    assert t.win_loss == "win"


def test_buy_sell_normalization():
    data = _csv(
        "entry_time,direction,entry_price,net_r",
        "2024-01-02 09:00:00,BUY,100.0,1.0",
        "2024-01-03 09:00:00,Sell,100.0,-1.0",
    )
    trades, skipped = parse_csv(data)
    assert skipped == 0
    assert [t.direction for t in trades] == ["long", "short"]


def test_nan_and_empty_become_none():
    data = _csv(
        "entry_time,direction,entry_price,sl_price,exit_price,net_r",
        "2024-01-02 09:00:00,long,NaN,,#DIV/0!,0.5",
    )
    trades, skipped = parse_csv(data)
    assert skipped == 0
    t = trades[0]
    assert t.entry is None
    assert t.sl is None
    assert t.exit is None
    assert t.r_value == 0.5


def test_broken_row_skipped_and_counted():
    data = _csv(
        "entry_time,direction,entry_price,net_r",
        "2024-01-02 09:00:00,long,100.0,1.0",
        "notadate,,notanumber,",  # nothing parseable -> skip
        ",,,",  # empty -> skip
        "2024-01-04 09:00:00,short,100.0,-1.0",
    )
    trades, skipped = parse_csv(data)
    assert len(trades) == 2
    assert skipped == 2


def test_discarded_columns_are_never_persisted():
    data = _csv(
        "entry_time,exit_time,direction,entry_price,tp_price,exit_reason,gross_r,net_r",
        "2024-03-01 12:00:00,2024-03-01 13:00:00,long,100.0,110.0,tp,5.0,2.0",
    )
    trades, _ = parse_csv(data)
    t = trades[0]
    field_names = {f.name for f in fields(t)}
    # None of the discarded columns leak into the ParsedTrade shape.
    for discarded in ("gross_r", "exit_reason", "tp_price", "exit_time"):
        assert discarded not in field_names
    # r_value carries net_r (2.0), never gross_r (5.0).
    assert t.r_value == 2.0


def test_header_without_known_columns_raises():
    data = _csv(
        "foo,bar,baz",
        "1,2,3",
    )
    with pytest.raises(ValueError):
        parse_csv(data)


def test_win_loss_derived_from_net_r():
    data = _csv(
        "entry_time,direction,entry_price,net_r",
        "2024-01-02 09:00:00,long,100.0,2.0",  # win
        "2024-01-03 09:00:00,short,100.0,-1.0",  # loss
        "2024-01-04 09:00:00,long,100.0,0.0",  # draw
        "2024-01-05 09:00:00,long,100.0,-0.05",  # blank zone -> None
    )
    trades, _ = parse_csv(data)
    assert [t.win_loss for t in trades] == ["win", "loss", "draw", None]


def test_iso_t_and_dotted_datetime_formats():
    data = _csv(
        "entry_time,direction,entry_price,net_r",
        "2024-03-01T12:30:00,long,100.0,1.0",
        "01.03.2024 08:15,short,100.0,-1.0",
        "2024-03-02 09:00,long,100.0,1.0",
    )
    trades, skipped = parse_csv(data)
    assert skipped == 0
    assert trades[0].trade_datetime == datetime(2024, 3, 1, 12, 30, 0)
    assert trades[1].trade_datetime == datetime(2024, 3, 1, 8, 15)
    assert trades[2].trade_datetime == datetime(2024, 3, 2, 9, 0)
