"""Set lifecycle data — release dates, OOP status, est. discontinuation.

Pokemon Company doesn't publish official out-of-print dates, so this is
hand-curated from community sources (PWCC, Card Cavalcade, etc.).
"""
import json
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
LIFECYCLE_PATH = _HERE / "set_lifecycle.json"


def load_lifecycle() -> dict[str, dict]:
    with open(LIFECYCLE_PATH) as f:
        data = json.load(f)
    # _meta is a documentation entry, not a set
    return {k: v for k, v in data.items() if not k.startswith("_")}


def months_since(release_date_str: str | None) -> int | None:
    if not release_date_str:
        return None
    try:
        d = datetime.strptime(release_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    return (today.year - d.year) * 12 + (today.month - d.month)
