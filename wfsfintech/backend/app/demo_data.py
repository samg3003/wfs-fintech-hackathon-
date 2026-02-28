"""
Demo data and stubbed quant logic for AdvisorIQ.

This module generates deterministic, synthetic data that matches the
shapes of the real system so the web platform can run end-to-end
without live market data or trained models.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Tuple

import numpy as np

from .iv_fetcher import IVFetchError, get_stock_iv_cached
from .domain import (
    ClientProfile,
    NarrativeExplanation,
    PortfolioComparison,
    PortfolioWeights,
    RegimeName,
    StressTestResult,
    TickerSignal,
)


RNG = np.random.default_rng(seed=42)


def get_universe() -> List[str]:
    return [
        "AAPL",
        "MSFT",
        "NVDA",
        "GOOGL",
        "AMZN",
        "META",
        "SPY",
        "HYG",
        "TLT",
        "XLE",
        "XLV",
        "XLF",
    ]


def get_demo_regime() -> RegimeName:
    # Simple cyclic regime based on day of month
    day = date.today().day
    if day % 4 == 0:
        return "CRISIS"
    if day % 3 == 0:
        return "STRESS"
    if day % 2 == 0:
        return "NORMAL"
    return "LOW_VOL"


def generate_ticker_signals() -> List[TickerSignal]:
    regime = get_demo_regime()
    universe = get_universe()
    signals: List[TickerSignal] = []

    base_iv_by_regime: Dict[RegimeName, float] = {
        "LOW_VOL": 0.15,
        "NORMAL": 0.20,
        "STRESS": 0.30,
        "CRISIS": 0.45,
    }
    ivr_thresholds: Dict[RegimeName, float] = {
        "LOW_VOL": 1.2,
        "NORMAL": 1.5,
        "STRESS": 1.8,
        "CRISIS": 2.0,
    }

    base_iv = base_iv_by_regime[regime]
    threshold = ivr_thresholds[regime]

    for i, symbol in enumerate(universe):
        noise = 0.02 * math.sin(i) + 0.01 * (i % 3)
        # Try cache-first options IV; fall back to synthetic if unavailable.
        try:
            iv = float(get_stock_iv_cached(symbol, refresh=False))
        except (IVFetchError, Exception):
            iv = max(0.05, base_iv + noise)
        predicted_hv = max(0.05, iv / (1.1 + 0.1 * math.cos(i)))
        ivr = iv / predicted_hv
        iv_percentile = min(1.0, max(0.0, 0.7 + 0.03 * (i % 5)))

        fear_level = "NONE"
        recommended_action = "Hold position"
        if ivr > threshold and iv_percentile >= 0.8:
            if ivr > threshold + 0.3:
                fear_level = "HIGH_FEAR"
                recommended_action = "Reduce position significantly"
            else:
                fear_level = "ELEVATED_FEAR"
                recommended_action = "Trim position moderately"

        signals.append(
            TickerSignal(
                symbol=symbol,
                iv=iv,
                predicted_hv=predicted_hv,
                ivr=ivr,
                iv_percentile=iv_percentile,
                regime=regime,
                fear_level=fear_level,
                recommended_action=recommended_action,
            )
        )

    return signals


def get_demo_clients() -> List[ClientProfile]:
    from .clients_store import get_all_clients
    return get_all_clients()


def _demo_current_weights(universe: List[str]) -> Dict[str, float]:
    raw = RNG.random(len(universe))
    raw = raw / raw.sum()
    return {s: float(w) for s, w in zip(universe, raw)}


def _scale_vol_to_target(base_vol: float, target_vol: float) -> float:
    return target_vol * (0.9 + 0.2 * (base_vol > target_vol))


def _make_portfolio(
    as_of: str, weights: Dict[str, float], target_vol: float, risk_multiplier: float
) -> PortfolioWeights:
    # Simple demo: expected_vol scales with risk_multiplier and target_vol
    expected_vol = _scale_vol_to_target(target_vol * risk_multiplier, target_vol)
    expected_return = 0.06 + 0.5 * expected_vol
    sharpe = expected_return / expected_vol if expected_vol > 0 else 0.0
    return PortfolioWeights(
        as_of=as_of,
        weights=weights,
        expected_return=expected_return,
        expected_vol=expected_vol,
        sharpe=sharpe,
    )


def generate_portfolio_comparisons() -> List[PortfolioComparison]:
    today = date.today().isoformat()
    universe = get_universe()
    clients = get_demo_clients()

    base_current = _demo_current_weights(universe)
    signals = {s.symbol: s for s in generate_ticker_signals()}

    results: List[PortfolioComparison] = []

    for client in clients:
        # Create client-specific tweaks to current weights
        tilt_factor = 1.0 + 0.1 * (
            1 if client.risk_label in ("AGGRESSIVE",) else -1
        )
        current_weights = {
            symbol: max(0.0, min(1.0, w * tilt_factor))
            for symbol, w in base_current.items()
        }
        total = sum(current_weights.values()) or 1.0
        current_weights = {k: v / total for k, v in current_weights.items()}

        baseline_optimal_weights = {
            s: float(max(0.0, w * RNG.normal(1.0, 0.05)))
            for s, w in current_weights.items()
        }
        total_b = sum(baseline_optimal_weights.values()) or 1.0
        baseline_optimal_weights = {k: v / total_b for k, v in baseline_optimal_weights.items()}

        iv_adjusted_weights = {}
        for s, w in baseline_optimal_weights.items():
            signal = signals.get(s)
            if signal and signal.fear_level != "NONE":
                trim = 0.4 if signal.fear_level == "HIGH_FEAR" else 0.2
                iv_adjusted_weights[s] = max(0.0, w * (1.0 - trim))
            else:
                iv_adjusted_weights[s] = w
        total_iv = sum(iv_adjusted_weights.values()) or 1.0
        iv_adjusted_weights = {k: v / total_iv for k, v in iv_adjusted_weights.items()}

        baseline_port = _make_portfolio(
            today, baseline_optimal_weights, client.target_annual_vol, risk_multiplier=1.0
        )
        iv_adjusted_port = _make_portfolio(
            today, iv_adjusted_weights, client.target_annual_vol, risk_multiplier=0.9
        )

        drift = {
            s: float(iv_adjusted_weights.get(s, 0.0) - current_weights.get(s, 0.0))
            for s in universe
        }

        current_annual_vol = _scale_vol_to_target(
            client.target_annual_vol * (1.1 if client.risk_label == "AGGRESSIVE" else 0.95),
            client.target_annual_vol,
        )
        misaligned = abs(current_annual_vol - client.target_annual_vol) > 0.03

        results.append(
            PortfolioComparison(
                client=client,
                current_weights=current_weights,
                baseline_optimal=baseline_port,
                iv_adjusted_optimal=iv_adjusted_port,
                drift_from_optimal=drift,
                current_annual_vol=current_annual_vol,
                misaligned_with_profile=misaligned,
            )
        )

    return results


def generate_stress_tests() -> List[StressTestResult]:
    comparisons = generate_portfolio_comparisons()
    avg_vol_current = float(
        np.mean([c.current_annual_vol for c in comparisons])
    )
    avg_vol_iv = float(
        np.mean([c.iv_adjusted_optimal.expected_vol for c in comparisons])
    )

    scenarios: List[Tuple[str, str, float, float]] = [
        (
            "2008_GFC",
            "Global Financial Crisis-style equity meltdown with flight to quality in Treasuries.",
            -0.45,
            -0.32,
        ),
        (
            "2020_COVID",
            "COVID crash with sharp but brief volatility spike and rapid policy response.",
            -0.35,
            -0.24,
        ),
        (
            "2022_RATE_SHOCK",
            "Rate shock where both equities and bonds sell off together.",
            -0.30,
            -0.21,
        ),
    ]

    results: List[StressTestResult] = []
    for name, desc, base_shock, iv_shock in scenarios:
        loss_current = base_shock * (avg_vol_current / 0.20)
        loss_iv_adj = iv_shock * (avg_vol_iv / 0.18)
        results.append(
            StressTestResult(
                name=name,
                description=desc,
                portfolio_loss_pct_current=loss_current,
                portfolio_loss_pct_iv_adjusted=loss_iv_adj,
            )
        )

    # VIX doubling scenario: assume IV-adjusted portfolio is more stable
    vix_double_loss_current = -0.25 * (avg_vol_current / 0.20)
    vix_double_loss_iv = -0.17 * (avg_vol_iv / 0.18)
    results.append(
        StressTestResult(
            name="VIX_DOUBLING",
            description="Hypothetical scenario where implied volatility doubles overnight across the universe.",
            portfolio_loss_pct_current=vix_double_loss_current,
            portfolio_loss_pct_iv_adjusted=vix_double_loss_iv,
        )
    )

    return results


def generate_narrative_for_client(client_id: str) -> NarrativeExplanation:
    regime = get_demo_regime()
    signals = generate_ticker_signals()
    portfolios = {c.client.client_id: c for c in generate_portfolio_comparisons()}
    portfolio = portfolios.get(client_id)

    top_fear = [s for s in signals if s.fear_level != "NONE"]
    top_fear = sorted(top_fear, key=lambda s: s.ivr, reverse=True)[:3]

    if not portfolio:
        title = "Portfolio summary"
        intro = "Here is a high-level summary of your portfolio using options-implied risk."
        key_points: List[str] = []
    else:
        title = f"{portfolio.client.name}'s options-informed portfolio check-up"
        intro = (
            f"We analysed your current holdings against an options-market-informed "
            f"target portfolio calibrated to your {portfolio.client.risk_label.lower()} "
            f"risk profile."
        )
        key_points = [
            f"Your current portfolio volatility is approximately {portfolio.current_annual_vol:.1%} "
            f"versus a target of {portfolio.client.target_annual_vol:.1%}.",
            f"The IV-adjusted optimal portfolio improves the expected Sharpe ratio from "
            f"{portfolio.baseline_optimal.sharpe:.2f} to {portfolio.iv_adjusted_optimal.sharpe:.2f}.",
        ]

    if top_fear:
        names = ", ".join(s.symbol for s in top_fear)
        key_points.append(
            f"The options market is currently pricing elevated risk in {names}, "
            f"which leads the system to recommend trimming these positions."
        )

    body = (
        f"{intro}\n\n"
        f"In the current {regime.replace('_', ' ').title()} regime, we pay close "
        f"attention to where implied volatility diverges from model-predicted realised "
        f"volatility. The system highlights names where options-implied risk is both "
        f"high relative to history and high relative to what recent price behaviour alone "
        f"would suggest. Those names are treated as riskier in the optimisation, so your "
        f"recommended allocation automatically tilts away from them without trying to time "
        f"short-term price moves.\n\n"
        f"The result is a portfolio that better aligns with your stated risk tolerance while "
        f"respecting the information embedded in the options market. You can review the "
        f"suggested trades and stress-test views in the dashboard, and discuss any changes "
        f"with your advisor."
    )

    return NarrativeExplanation(
        client_id=client_id,
        title=title,
        body=body,
        key_points=key_points,
        regime=regime,
        top_fear_signals=top_fear,
    )

