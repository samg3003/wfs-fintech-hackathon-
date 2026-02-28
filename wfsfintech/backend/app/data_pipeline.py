"""
Data Pipeline — Institutional quant preprocessing (all 8 steps from the guide).

Step 1: Handling missing values — forward-fill only, no back-fill, no dropna
Step 2: Aligning timestamps — strict inner join on dates
Step 3: Log returns, not simple percentage returns
Step 4: Annualise volatility with √252
Step 5: Feature matrix construction (for vol forecaster — placeholder)
Step 6: Scaling for regime classifier (standardise: mean 0, std 1)
Step 7: Temporal integrity — train/val/test splits, no leakage
Step 8: Cache to parquet, load from disk
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from .config import CACHE_DIR


TRADING_DAYS_PER_YEAR = 252


# --- Step 1: Missing Values ---


def forward_fill_prices(raw_data: pd.DataFrame) -> pd.DataFrame:
    """
    Step 1: Forward-fill only. Carry last valid observation forward.
    Never interpolate or back-fill financial prices.
    Do not drop rows — that creates gaps that break rolling calculations.
    """
    return raw_data.ffill()


# --- Step 2: Aligning Timestamps ---


def align_timestamps(data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame] | pd.DataFrame:
    """
    Step 2: Merge on intersection of trading dates.
    Any date missing from any series gets dropped (strict inner join on date axis).
    """
    if len(data_dict) == 1:
        # Return the single DataFrame unchanged
        return list(data_dict.values())[0]

    # Get intersection of all valid dates
    common_index = None
    for df in data_dict.values():
        valid_dates = df.dropna(how="all").index
        if common_index is None:
            common_index = valid_dates
        else:
            common_index = common_index.intersection(valid_dates)

    if common_index is None:
        return data_dict

    # Align all series to common dates
    aligned: Dict[str, pd.DataFrame] = {}
    for name, df in data_dict.items():
        aligned[name] = df.loc[common_index].copy()

    return aligned


def align_prices_to_common_dates(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Step 2 (single DataFrame): Keep only dates where ALL tickers have valid data.
    Strict inner join.
    """
    data = prices_df.dropna(how="any")
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="first")]
    return data


# --- Step 3: Log Returns ---


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Step 3: Log returns, not price changes or simple percentage returns.
    log_return = ln(price_t / price_{t-1})
    - Approximately normal for short horizons
    - Additive across time (10-day log return = sum of 10 daily log returns)
    """
    return np.log(prices / prices.shift(1)).dropna()


# --- Step 4: Annualising Volatility ---


def annualise_volatility(daily_vol: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """
    Step 4: Multiply daily volatility by √252.
    Makes HV comparable to IV (always quoted annualised).
    """
    return daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR)


def annualise_return(daily_return: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Annualise daily log return."""
    return daily_return * TRADING_DAYS_PER_YEAR


# --- Step 5: Feature Matrix (placeholder for vol forecaster) ---


def build_feature_matrix(
    prices: pd.DataFrame,
    returns: Optional[pd.DataFrame] = None,
    target_window: int = 30,
    feature_lags: Optional[Iterable[int]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 5: For each ticker/date, compute features and align with forward-looking target.
    Forward target for date T = realised vol from T+1 to T+30.
    Rows at boundary where target extends into validation period are dropped.

    Currently returns:
    - log_ret: daily log returns
    - realised_vol: rolling realised volatility (annualised)
    """
    if feature_lags is None:
        feature_lags = [1, 5, 10, 21]

    # Placeholder — extend when building vol forecaster
    log_ret = compute_log_returns(prices) if returns is None else returns
    realised_vol = log_ret.rolling(target_window).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    return log_ret, realised_vol


# --- Step 6: Scaling for Regime Classifier ---


def standardise_features(
    X: pd.DataFrame,
    train_mean: Optional[pd.Series] = None,
    train_std: Optional[pd.Series] = None,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Step 6: Standardise — subtract mean, divide by std.
    Compute mean/std on TRAINING data only. Apply same transform to val/test.
    Never compute scaling stats on test set (data leakage).
    """
    if train_mean is None:
        train_mean = X.mean()
    if train_std is None:
        train_std = X.std().replace(0, np.nan)
    X_scaled = (X - train_mean) / train_std
    return X_scaled, train_mean, train_std


# --- Step 7: Temporal Integrity ---


def temporal_split(
    data: pd.DataFrame,
    train_end: pd.Timestamp,
    val_end: pd.Timestamp,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Step 7: No overlap between train/val/test.
    train_end, val_end are the last date IN each set.
    """
    train = data[data.index <= train_end]
    val = data[(data.index > train_end) & (data.index <= val_end)]
    test = data[data.index > val_end]
    return train, val, test


# --- Step 8: Caching ---


def _cache_path(key: str, suffix: str) -> str:
    path = CACHE_DIR / f"{key}_{suffix}.parquet"
    return str(path)


def _cache_key(tickers: List[str], start: str, end: str) -> str:
    s = "_".join(sorted(tickers)) + f"_{start}_{end}".replace("-", "")
    return hashlib.md5(s.encode()).hexdigest()[:16]


def load_from_cache(
    tickers: List[str],
    start: str,
    end: str,
) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Step 8: Load preprocessed data from disk."""
    key = _cache_key(tickers, start, end)
    prices_path = _cache_path(key, "prices")
    returns_path = _cache_path(key, "returns")
    if os.path.exists(prices_path) and os.path.exists(returns_path):
        return pd.read_parquet(prices_path), pd.read_parquet(returns_path)
    return None


def save_to_cache(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    tickers: List[str],
    start: str,
    end: str,
) -> None:
    """Step 8: Save preprocessed data to disk."""
    key = _cache_key(tickers, start, end)
    prices.to_parquet(_cache_path(key, "prices"))
    returns.to_parquet(_cache_path(key, "returns"))


# --- Full Pipeline ---


def fetch_price_data(
    tickers: List[str] | str,
    start: str = "2021-01-01",
    end: str = "2024-01-01",
) -> pd.DataFrame:
    """Fetch raw Close prices from Yahoo Finance."""
    if isinstance(tickers, str):
        tickers = [tickers]
    raw = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            raw = raw["Close"].copy()
        if isinstance(raw, pd.Series):
            raw = raw.to_frame()
        raw.columns = tickers
    else:
        if "Close" in raw.columns:
            raw = raw[["Close"]].copy()
        raw.columns = tickers

    print(f"Raw data shape: {raw.shape}")
    return raw


def clean_price_data(raw_data: pd.DataFrame) -> pd.DataFrame:
    """Steps 1 & 2: Forward-fill + align timestamps (inner join)."""
    data = forward_fill_prices(raw_data)
    data = align_prices_to_common_dates(data)
    print(f"Cleaned data shape: {data.shape}")
    return data


def validate_data(data: pd.DataFrame, min_rows: int = 500) -> bool:
    """Gate check before data enters the optimiser."""
    checks = []
    checks.append(len(data) >= min_rows)
    checks.append(len(data.columns) >= 2)
    checks.append(not data.isnull().any().any())
    checks.append(not (data <= 0).any().any())
    for msg, ok in [
        (f"PASS: {len(data)} trading days", checks[0]),
        (f"PASS: {len(data.columns)} assets", checks[1]),
        ("PASS: No missing values", checks[2]),
        ("PASS: All prices positive", checks[3]),
    ]:
        print(msg if ok else msg.replace("PASS", "FAIL"))
    return all(checks)


def get_clean_data(
    tickers: List[str] | str,
    start: str = "2021-01-01",
    end: str = "2024-01-01",
    use_cache: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Full pipeline: fetch → clean (Steps 1–2) → validate → log returns (Step 3).
    Step 8: Load from cache if available, else compute and save.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = sorted(set(tickers))

    if use_cache:
        cached = load_from_cache(tickers, start, end)
        if cached is not None:
            print(f"Loaded from cache: {CACHE_DIR}")
            return cached

    raw = fetch_price_data(tickers, start, end)
    cleaned = clean_price_data(raw)
    if not validate_data(cleaned):
        raise ValueError("Data failed validation.")

    returns = compute_log_returns(cleaned)

    if use_cache:
        save_to_cache(cleaned, returns, tickers, start, end)
        print(f"Cached to {CACHE_DIR}")

    return cleaned, returns


def fetch_benchmark(
    start: str = "2021-01-01",
    end: str = "2024-01-01",
) -> pd.Series:
    """Pull S&P 500 benchmark."""
    raw = yf.download("^GSPC", start=start, end=end, progress=False)
    if "Close" in raw.columns:
        col = raw["Close"]
    elif "Adj Close" in raw.columns:
        col = raw["Adj Close"]
    else:
        col = raw.iloc[:, 0]
    return col.ffill().dropna()


def fetch_risk_free_rate() -> float:
    """Pull 10-year Treasury yield (annualised, decimal)."""
    tnx = yf.download("^TNX", progress=False)
    if "Close" in tnx.columns:
        col = tnx["Close"]
    elif "Adj Close" in tnx.columns:
        col = tnx["Adj Close"]
    else:
        col = tnx.iloc[:, 0]
    return float(col.iloc[-1] / 100)

