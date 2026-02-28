# AdvisorIQ

Options-informed portfolio intelligence for advisors. Uses implied volatility from the options market to adjust portfolio optimisation and surface risk signals before they materialise in price data.

## Quick start

```bash
# Create venv and install dependencies (one-time)
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# Run the full stack (serves frontend + API on port 8000)
./run.sh
# Or: PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000

**Login**: `advisor@advisoriq.com` / `advisor123`

## Alternative: separate static server

If you prefer to run the frontend and backend separately:

```bash
# Terminal 1: API
cd backend && uvicorn app.main:app --reload --port 8001 --app-dir .

# Terminal 2: Static files (edit app.js: set API_BASE = "http://localhost:8001")
python3 -m http.server 8000
```

## Architecture

- **Data layer**: Cached asset prices, macro series (VIX, SPY, HYG, TLT), ATM IV per ticker
- **ML Layer A**: Vol forecaster (XGBoost) — predicted 30d HV for IVR denominator
- **ML Layer B**: Regime classifier (HMM) — LOW_VOL, NORMAL, STRESS, CRISIS
- **IVR Signal Engine**: IVR = IV / predicted_HV; regime-dependent thresholds; IV percentile filter
- **IV-adjusted optimisation**: Replace diagonal of covariance with IV-implied variance; keep correlations historical
- **Multi-client layer**: Five client profiles; drift, rebalancing, risk misalignment
- **Stress test engine**: Historical scenarios (2008, 2020, 2022) + VIX doubling
- **LLM layer**: Translates structured outputs into client-ready narrative

The demo uses synthetic data. Replace `demo_data.py` with real cached data and trained models for production.

## Login & onboarding

- **Advisor login**: `advisor@advisoriq.com` / `advisor123`
- **Onboard client**: After login, use "Onboard client" in the nav to add new clients. They are persisted to `backend/data/clients.json` and appear in the triage dashboard.
