"""Advisor authentication — JWT-based login."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

SECRET_KEY = "advisoriq-demo-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Demo advisor: advisor@advisoriq.com / advisor123 (hash for demo only)
DEMO_PASSWORD_HASH = hashlib.sha256(b"advisor123-advisoriq-salt").hexdigest()


def _hash_password(password: str) -> str:
    return hashlib.sha256((password + "-advisoriq-salt").encode()).hexdigest()


def create_access_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def authenticate_advisor(email: str, password: str) -> Optional[dict]:
    if email != "advisor@advisoriq.com":
        return None
    if _hash_password(password) != DEMO_PASSWORD_HASH:
        return None
    return {"email": email, "name": "Demo Advisor"}
