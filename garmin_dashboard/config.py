"""Environment based configuration. No secrets are logged or displayed."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
DATABASE_PATH = Path(os.getenv("GARMIN_DATABASE_PATH", PROJECT_ROOT / "data" / "garmin.sqlite3"))
GARMIN_API_KEY = os.getenv("GARMIN_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
