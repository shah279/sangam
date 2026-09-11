"""EOD close-price cache, fetched from Yahoo Finance's free chart API (no key,
no compiled deps — a plain httpx GET). NSE/BSE has no official free EOD feed,
and Yahoo mirrors both, so this is the source for price_points.

Each run re-fetches ~2 years of daily closes per symbol (one HTTP call each)
instead of just the latest bar: on a symbol's first run this backfills
history, so mentions made months ago already have an entry price for the
creator scorecard rather than only accumulating from today onward. Upserts on
(symbol, price_date) make re-fetching the same range every day a no-op for
rows that were already cached.

Only symbols already resolved on a mention (mentions.resolved_symbol) are
priced, and only on trading days: NSE/BSE are closed on weekends, so running
this stage then would just re-confirm data that's already cached.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import db
from .outcome import StageResult

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HISTORY_RANGE = "2y"

# normalize.py uses these prefixes for symbols already qualified to a foreign
# exchange; Yahoo wants the bare ticker for those instead of an NSE suffix.
_FOREIGN_PREFIXES = ("NASDAQ:", "NYSE:")
# The app's "Add to radar" dialog uses this prefix for a BSE-only pick (one
# with no NSE listing) — Yahoo wants a ".BO" suffix for those, not ".NS".
_BSE_PREFIX = "BSE:"
# Non-equity resolved_symbol namespaces (sectors, indices, mutual funds, ...)
# don't have a Yahoo EOD close in this scheme yet.
_UNPRICEABLE_PREFIXES = ("MF:", "SECTOR:", "INDEX:", "GROUP:", "COMMODITY:")


def yahoo_ticker(symbol: str) -> str | None:
    """Map a resolved_symbol to the ticker Yahoo expects, or None if unsupported."""
    for prefix in _FOREIGN_PREFIXES:
        if symbol.startswith(prefix):
            return symbol[len(prefix):]
    if symbol.startswith(_BSE_PREFIX):
        return f"{symbol[len(_BSE_PREFIX):]}.BO"
    if symbol.startswith(_UNPRICEABLE_PREFIXES):
        return None
    return f"{symbol}.NS"


def is_trading_day(moment: datetime) -> bool:
    return moment.weekday() < 5  # Mon-Fri; rare NSE holidays just no-op below


def fetch_history(ticker: str) -> list[tuple[str, float]]:
    """Return [(ISO date, close), ...] for the configured lookback range."""
    r = db.fetch_external(
        YAHOO_CHART_URL.format(ticker=ticker),
        params={"interval": "1d", "range": HISTORY_RANGE},
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    results = (r.json().get("chart") or {}).get("result") or []
    if not results:
        return []
    payload = results[0]
    timestamps = payload.get("timestamp") or []
    quote = ((payload.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    return [
        (datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(), round(float(close), 4))
        for ts, close in zip(timestamps, closes)
        if close is not None
    ]


def run() -> StageResult:
    if not is_trading_day(datetime.now(timezone.utc)):
        print("prices: market closed today, skipping")
        return StageResult("prices", 0, 0)

    symbols = db.symbols_needing_prices()
    points: list[dict] = []
    errors: list[str] = []
    priced_symbols = 0
    for symbol in symbols:
        ticker = yahoo_ticker(symbol)
        if not ticker:
            continue
        try:
            history = fetch_history(ticker)
        except httpx.HTTPError as e:
            errors.append(f"{symbol}: {e}")
            continue
        if history:
            priced_symbols += 1
            points.extend(
                {"symbol": symbol, "price_date": price_date, "close": close}
                for price_date, close in history
            )

    with db.connect() as conn:
        updated = db.upsert_price_points(conn, points)
    print(f"prices: {priced_symbols}/{len(symbols)} symbol(s) updated ({updated} price point(s))")
    return StageResult("prices", priced_symbols, len(symbols), errors)


if __name__ == "__main__":
    raise SystemExit(0 if run().ok else 1)
