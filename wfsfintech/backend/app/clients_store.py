"""Persistent client storage — merge seeded demo clients with onboarded clients."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from .config import DATA_DIR
from .domain import ClientProfile

CLIENTS_FILE = DATA_DIR / "clients.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SEEDED_CLIENTS: List[ClientProfile] = [
    ClientProfile(client_id="margaret", name="Margaret Lee", risk_label="CONSERVATIVE", target_annual_vol=0.08),
    ClientProfile(client_id="sofia", name="Sofia Martinez", risk_label="MODERATE", target_annual_vol=0.12),
    ClientProfile(client_id="david", name="David Chen", risk_label="AGGRESSIVE", target_annual_vol=0.18),
    ClientProfile(client_id="amina", name="Amina Patel", risk_label="MODERATE", target_annual_vol=0.14),
    ClientProfile(client_id="liam", name="Liam O'Brien", risk_label="AGGRESSIVE", target_annual_vol=0.20),
]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "client"


def _load_custom() -> List[dict]:
    if not CLIENTS_FILE.exists():
        return []
    try:
        with open(CLIENTS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_custom(clients: List[dict]) -> None:
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)


def get_all_clients() -> List[ClientProfile]:
    custom = _load_custom()
    seeded_ids = {c.client_id for c in SEEDED_CLIENTS}
    result = list(SEEDED_CLIENTS)
    for raw in custom:
        cid = raw.get("client_id")
        if cid and cid not in seeded_ids:
            result.append(
                ClientProfile(
                    client_id=cid,
                    name=raw.get("name", "Unknown"),
                    risk_label=raw.get("risk_label", "MODERATE"),
                    target_annual_vol=float(raw.get("target_annual_vol", 0.12)),
                )
            )
    return result


def add_client(name: str, risk_label: str, target_annual_vol: float) -> ClientProfile:
    base_id = _slug(name)
    custom = _load_custom()
    existing_ids = {c["client_id"] for c in custom} | {c.client_id for c in SEEDED_CLIENTS}
    client_id = base_id
    n = 1
    while client_id in existing_ids:
        client_id = f"{base_id}-{n}"
        n += 1

    new_client = {
        "client_id": client_id,
        "name": name,
        "risk_label": risk_label,
        "target_annual_vol": target_annual_vol,
    }
    custom.append(new_client)
    _save_custom(custom)

    return ClientProfile(
        client_id=client_id,
        name=name,
        risk_label=risk_label,
        target_annual_vol=target_annual_vol,
    )
