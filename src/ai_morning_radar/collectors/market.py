from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ..config import all_instruments
from ..models import MarketSnapshot


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize_snapshot(
    instrument: dict[str, Any],
    closes: list[float],
    timestamps: list[datetime],
    now: datetime | None = None,
    previous_close_override: float | None = None,
) -> MarketSnapshot:
    """把不同市场的收盘序列标准化为统一行情快照。"""
    now = now or datetime.now(timezone.utc)
    clean = [v for value in closes if (v := _number(value)) is not None]
    price = clean[-1] if clean else None
    previous = previous_close_override if previous_close_override is not None else (clean[-2] if len(clean) >= 2 else None)
    change_pct = None
    if price is not None and previous not in (None, 0):
        change_pct = (price / previous - 1) * 100
    last_at = timestamps[-1] if timestamps else now
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    stale = max(0, int((now.astimezone(timezone.utc) - last_at.astimezone(timezone.utc)).total_seconds() / 60))
    status = "missing" if price is None else ("stale" if stale > 24 * 60 else "ok")
    change_bps = None
    if instrument.get("change_unit") == "bp" and price is not None and previous is not None:
        # Yahoo has used both 4.12-style and 41.2-style ^TNX quote conventions.
        multiplier = 10 if max(abs(price), abs(previous)) > 20 else 100
        change_bps = (price - previous) * multiplier
    return MarketSnapshot(
        symbol=instrument["symbol"],
        name=instrument["name"],
        category=instrument["category"],
        price=price,
        change_pct=change_pct,
        previous_close=previous,
        as_of=last_at.isoformat(),
        session="韩国当日5分钟（定时任务08:50截取）" if instrument["category"] == "korea" else "最近两个交易日",
        status=status,
        stale_minutes=stale,
        change_bps=change_bps,
        sparkline=clean[-24:],
        evidence_id=f"MKT-{instrument['symbol']}",
    )


def collect_market(config: dict[str, Any], groups: set[str] | None = None) -> list[MarketSnapshot]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:
        raise RuntimeError("真实行情需要安装 yfinance：python -m pip install -e .") from exc

    instruments = all_instruments(config, groups)
    result: list[MarketSnapshot] = []
    now = datetime.now(timezone.utc)
    for instrument in instruments:
        try:
            ticker = yf.Ticker(instrument["symbol"])
            if instrument["category"] == "korea":
                frame = ticker.history(period="2d", interval="5m", auto_adjust=False, prepost=False)
                if not frame.empty:
                    latest_day = frame.index[-1].date()
                    current = frame[frame.index.date == latest_day]
                    previous = frame[frame.index.date < latest_day]
                    # Compare the latest intraday quote with the prior session close,
                    # while preserving today's 5-minute path for the sparkline.
                    prior_close = float(previous["Close"].dropna().iloc[-1]) if not previous.empty else None
                    closes = current["Close"].dropna().tolist()
                    timestamps = [ts.to_pydatetime() for ts in current.index]
                    result.append(normalize_snapshot(instrument, closes, timestamps, now, prior_close))
                    continue
            else:
                frame = ticker.history(period="10d", interval="1d", auto_adjust=False)
            closes = frame["Close"].dropna().tolist() if not frame.empty else []
            timestamps = [ts.to_pydatetime() for ts in frame.index] if not frame.empty else []
            result.append(normalize_snapshot(instrument, closes, timestamps, now))
        except Exception as exc:  # one bad symbol must not abort the report
            result.append(MarketSnapshot(
                symbol=instrument["symbol"], name=instrument["name"], category=instrument["category"],
                price=None, change_pct=None, previous_close=None, as_of=now.isoformat(),
                status="error", session="采集失败", evidence_id=f"MKT-{instrument['symbol']}",
                source=f"Yahoo Finance / yfinance ({type(exc).__name__})",
            ))
    return result
