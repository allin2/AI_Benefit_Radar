import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DEFAULT_DB_PATH = DATA_DIR / "benefit_desk.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# Versions
PROTOCOL_VERSION = "0.1"
BENEFIT_SCHEMA_VERSION = "1.2.1"
APP_TITLE = "AI Benefit Desk V0.1"
