from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional


RegimeName = Literal["LOW_VOL", "NORMAL", "STRESS", "CRISIS"]
FearLevel = Literal["NONE", "ELEVATED_FEAR", "HIGH_FEAR"]


@dataclass
class TickerSignal:
    symbol: str
    iv: float
    predicted_hv: float
    ivr: float
    iv_percentile: float
    regime: RegimeName
    fear_level: FearLevel
    recommended_action: str


@dataclass
class ClientProfile:
    client_id: str
    name: str
    risk_label: Literal["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]
    target_annual_vol: float


@dataclass
class PortfolioWeights:
    as_of: str
    weights: Dict[str, float]
    expected_return: float
    expected_vol: float
    sharpe: float


@dataclass
class PortfolioComparison:
    client: ClientProfile
    current_weights: Dict[str, float]
    baseline_optimal: PortfolioWeights
    iv_adjusted_optimal: PortfolioWeights
    drift_from_optimal: Dict[str, float]
    current_annual_vol: float
    misaligned_with_profile: bool


@dataclass
class StressTestResult:
    name: str
    description: str
    portfolio_loss_pct_current: float
    portfolio_loss_pct_iv_adjusted: float


@dataclass
class NarrativeExplanation:
    client_id: str
    title: str
    body: str
    key_points: List[str]
    regime: RegimeName
    top_fear_signals: List[TickerSignal]

