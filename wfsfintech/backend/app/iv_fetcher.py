"""
SignalEngine — Compute implied volatility from options for individual stocks.

Cache-first: we write IV snapshots to disk so demos don't depend on live API calls.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf
from py_vollib.black_scholes.implied_volatility import implied_volatility

from .config import CACHE_DIR


class IVFetchError(ValueError):
    pass


def _safe_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol)


def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"iv_snapshot_{_safe_symbol(symbol)}.json"


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def get_stock_iv(ticker_symbol: str = "AAPL") -> float:
    """
    Get implied volatility for a stock/ETF from its ATM call option.
    Works for individual stocks/ETFs (AAPL, MSFT, NVDA, SPY, etc.).

    Notes:
    - Indices like SPX / ^GSPC often won't have an options chain here.
    - Prefers Yahoo's impliedVolatility field when present.
    - Falls back to computing IV using py_vollib if needed.
    """
    if ticker_symbol.startswith("^"):
        raise IVFetchError(
            f"No options data for {ticker_symbol}. Indices (e.g. ^GSPC) are not supported."
        )

    t = yf.Ticker(ticker_symbol)

    # Get spot price (S)
    S = t.info.get("currentPrice")
    if not S or not isinstance(S, (int, float)) or S <= 0:
        hist = t.history(period="5d")
        if hist.empty:
            raise IVFetchError(
                f"No price data found for {ticker_symbol}. Use a valid stock ticker (e.g. AAPL, MSFT)."
            )
        S = float(hist["Close"].iloc[-1])

    # Get options chain expirations
    exps = list(getattr(t, "options", []) or [])
    if not exps:
        raise IVFetchError(
            f"No options data for {ticker_symbol}. Indices (SPX, ^GSPC) are not supported."
        )

    # Nearest expiry
    expiry = exps[0]
    chain = t.option_chain(expiry)
    calls = chain.calls
    if calls is None or calls.empty:
        raise IVFetchError(f"No call options found for {ticker_symbol}.")

    # Pick ATM option
    atm = calls.loc[(calls["strike"] - S).abs().idxmin()]
    K = float(atm["strike"])

    # Prefer Yahoo IV if present
    if "impliedVolatility" in atm.index and pd.notna(atm["impliedVolatility"]):
        iv = float(atm["impliedVolatility"])
        if iv > 0 and math.isfinite(iv):
            return iv

    # Otherwise compute via mid price (fallback to lastPrice if needed)
    bid = float(atm["bid"]) if pd.notna(atm.get("bid")) else float("nan")
    ask = float(atm["ask"]) if pd.notna(atm.get("ask")) else float("nan")
    last = float(atm["lastPrice"]) if pd.notna(atm.get("lastPrice")) else float("nan")

    if math.isfinite(bid) and math.isfinite(ask) and bid > 0 and ask > 0:
        price = (bid + ask) / 2.0
    elif math.isfinite(last) and last > 0:
        price = last
    else:
        raise IVFetchError(f"Option price unavailable for {ticker_symbol} ({expiry} ATM).")

    days = (datetime.strptime(expiry, "%Y-%m-%d") - datetime.now()).days
    if days <= 1:
        raise IVFetchError(f"Expiry too close for robust IV: {ticker_symbol} {expiry}.")
    T = days / 365.0

    # Risk-free rate: demo constant
    r = 0.045
    return float(implied_volatility(price, S, K, T, r, "c"))


def get_stock_iv_cached(
    ticker_symbol: str, *, max_age_seconds: int = 60 * 60 * 24, refresh: bool = False
) -> float:
    """
    Cache-first IV fetch.

    - If cache is fresh, returns cached IV.
    - If refresh=False and cache is missing/stale, raises IVFetchError (no live calls).
    - If refresh=True, attempts a live fetch and writes cache.
    """
    path = _cache_path(ticker_symbol)
    cached = _read_json(path)
    now = int(time.time())

    if cached:
        fetched_at = int(cached.get("fetched_at", 0) or 0)
        iv = cached.get("iv")
        if isinstance(iv, (int, float)) and (now - fetched_at) <= max_age_seconds:
            return float(iv)

    if not refresh:
        raise IVFetchError(
            f"No fresh cached IV for {ticker_symbol}. Run with refresh=true to fetch and cache."
        )

    iv = get_stock_iv(ticker_symbol)
    _write_json(
        path,
        {
            "symbol": ticker_symbol,
            "iv": float(iv),
            "fetched_at": now,
        },
    )
    return float(iv)

