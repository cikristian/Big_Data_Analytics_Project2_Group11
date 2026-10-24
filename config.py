"""Shared settings for every script. Edit the connection values (or set the
environment variables) before running anything. Never commit real passwords."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

CAT = ZoneInfo("Africa/Kigali")

# Folder that holds the captured CSVs (kept local, not committed).
DATA_DIR = os.environ.get("MM_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

PG_DSN = os.environ.get(
    "MM_PG_DSN",
    "host=localhost port=5432 dbname=mobile_money user=postgres password=CHANGE_ME",
)
NEO4J_URI = os.environ.get("MM_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("MM_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("MM_NEO4J_PASSWORD", "CHANGE_ME")

# Investigation sets from section 4: (review account, destination, September day)
SETS = {
    "A": (998, 24755, 6),
    "B": (147228, 186823, 13),
    "C": (206978, 6573, 8),
    "D": (237998, 21755, 6),
    "E": (144228, 183823, 13),
    "F": (203978, 3573, 8),
}


def hour_bounds(day):
    """09:45:00 inclusive to 10:45:00 exclusive CAT on 2026-09-<day>, as epoch seconds."""
    start = datetime(2026, 9, day, 9, 45, 0, tzinfo=CAT)
    end = datetime(2026, 9, day, 10, 45, 0, tzinfo=CAT)
    return int(start.timestamp()), int(end.timestamp())


def cat(ts):
    """Epoch seconds -> readable CAT time string."""
    return datetime.fromtimestamp(ts, CAT).strftime("%Y-%m-%d %H:%M:%S CAT")


def csv_path(name):
    return os.path.join(DATA_DIR, f"{name}.csv")
