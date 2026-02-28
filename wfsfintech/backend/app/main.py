from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import authenticate_advisor, create_access_token, decode_token
from .clients_store import add_client
from .config import settings
from .demo_data import (
    generate_narrative_for_client,
    generate_portfolio_comparisons,
    generate_stress_tests,
    generate_ticker_signals,
    get_demo_clients,
    get_demo_regime,
    get_universe,
)
from .iv_fetcher import IVFetchError, get_stock_iv_cached


app = FastAPI(title=settings.app_name, version=settings.version)


def get_current_advisor(authorization: str | None = Header(None, alias="Authorization")) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    email = decode_token(token)
    if not email:
        return None
    return {"email": email, "name": "Demo Advisor"}


def require_advisor(authorization: str | None = Header(None, alias="Authorization")) -> dict:
    advisor = get_current_advisor(authorization)
    if not advisor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return advisor


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateClientRequest(BaseModel):
    name: str
    risk_label: str  # CONSERVATIVE | MODERATE | AGGRESSIVE
    target_annual_vol: float


@app.get("/api/options-iv")
def options_iv(
    refresh: bool = False, authorization: str | None = Header(None, alias="Authorization")
) -> dict:
    """
    Returns cache-first ATM IV per ticker in the universe.
    Set refresh=true to force live fetch and update cache.
    """
    require_advisor(authorization)
    ivs: dict = {}
    errors: dict = {}
    for symbol in get_universe():
        try:
            ivs[symbol] = get_stock_iv_cached(symbol, refresh=refresh)
        except IVFetchError as e:
            errors[symbol] = str(e)
        except Exception as e:
            errors[symbol] = f"Unexpected error: {e}"
    return {"iv": ivs, "errors": errors, "refresh": refresh}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/auth/login")
def login(req: LoginRequest) -> dict:
    advisor = authenticate_advisor(req.email, req.password)
    if not advisor:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(req.email)
    return {"token": token, "advisor": advisor}


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(None, alias="Authorization")) -> dict:
    advisor = get_current_advisor(authorization)
    if not advisor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"advisor": advisor}


@app.post("/api/clients")
def create_client(req: CreateClientRequest, authorization: str | None = Header(None, alias="Authorization")) -> dict:
    require_advisor(authorization)
    if req.risk_label not in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
        raise HTTPException(status_code=400, detail="Invalid risk_label")
    if not 0.04 <= req.target_annual_vol <= 0.35:
        raise HTTPException(status_code=400, detail="target_annual_vol must be between 0.04 and 0.35")
    client = add_client(req.name, req.risk_label, req.target_annual_vol)
    return {
        "client_id": client.client_id,
        "name": client.name,
        "risk_label": client.risk_label,
        "target_annual_vol": client.target_annual_vol,
    }


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/api/universe")
def universe() -> dict:
    # Optional: require auth for app data endpoints
    # Frontend sends Authorization automatically after login
    return {
        "tickers": get_universe(),
        "regime": get_demo_regime(),
    }


@app.get("/api/signals")
def signals() -> dict:
    sigs = generate_ticker_signals()
    return {
        "regime": sigs[0].regime if sigs else get_demo_regime(),
        "signals": [
            {
                "symbol": s.symbol,
                "iv": s.iv,
                "predicted_hv": s.predicted_hv,
                "ivr": s.ivr,
                "iv_percentile": s.iv_percentile,
                "regime": s.regime,
                "fear_level": s.fear_level,
                "recommended_action": s.recommended_action,
            }
            for s in sigs
        ],
    }


@app.get("/api/clients")
def clients() -> dict:
    return {
        "clients": [
            {
                "client_id": c.client_id,
                "name": c.name,
                "risk_label": c.risk_label,
                "target_annual_vol": c.target_annual_vol,
            }
            for c in get_demo_clients()
        ]
    }


@app.get("/api/portfolios")
def portfolios() -> dict:
    comps = generate_portfolio_comparisons()
    return {
        "portfolios": [
            {
                "client": {
                    "client_id": c.client.client_id,
                    "name": c.client.name,
                    "risk_label": c.client.risk_label,
                    "target_annual_vol": c.client.target_annual_vol,
                },
                "current_weights": c.current_weights,
                "baseline_optimal": {
                    "as_of": c.baseline_optimal.as_of,
                    "weights": c.baseline_optimal.weights,
                    "expected_return": c.baseline_optimal.expected_return,
                    "expected_vol": c.baseline_optimal.expected_vol,
                    "sharpe": c.baseline_optimal.sharpe,
                },
                "iv_adjusted_optimal": {
                    "as_of": c.iv_adjusted_optimal.as_of,
                    "weights": c.iv_adjusted_optimal.weights,
                    "expected_return": c.iv_adjusted_optimal.expected_return,
                    "expected_vol": c.iv_adjusted_optimal.expected_vol,
                    "sharpe": c.iv_adjusted_optimal.sharpe,
                },
                "drift_from_optimal": c.drift_from_optimal,
                "current_annual_vol": c.current_annual_vol,
                "misaligned_with_profile": c.misaligned_with_profile,
            }
            for c in comps
        ]
    }


@app.get("/api/stress-tests")
def stress_tests() -> dict:
    tests = generate_stress_tests()
    return {
        "scenarios": [
            {
                "name": t.name,
                "description": t.description,
                "portfolio_loss_pct_current": t.portfolio_loss_pct_current,
                "portfolio_loss_pct_iv_adjusted": t.portfolio_loss_pct_iv_adjusted,
            }
            for t in tests
        ]
    }


@app.get("/api/explain/{client_id}")
def explain(client_id: str) -> dict:
    clients = {c.client_id: c for c in get_demo_clients()}
    if client_id not in clients:
        raise HTTPException(status_code=404, detail="Client not found")
    narrative = generate_narrative_for_client(client_id)
    return {
        "client_id": narrative.client_id,
        "title": narrative.title,
        "body": narrative.body,
        "key_points": narrative.key_points,
        "regime": narrative.regime,
        "top_fear_signals": [
            {
                "symbol": s.symbol,
                "ivr": s.ivr,
                "fear_level": s.fear_level,
                "recommended_action": s.recommended_action,
            }
            for s in narrative.top_fear_signals
        ],
    }


# Serve frontend static files (must be last so /api routes take precedence)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if (PROJECT_ROOT / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(PROJECT_ROOT), html=True), name="static")

