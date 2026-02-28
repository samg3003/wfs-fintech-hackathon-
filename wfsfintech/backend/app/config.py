from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    app_name: str = "AdvisorIQ"
    version: str = "0.1.0"


settings = Settings()

