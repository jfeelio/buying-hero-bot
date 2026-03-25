import json
import logging
from pathlib import Path

SEEN_FILE = Path(__file__).parent / "seen_cases.json"

logger = logging.getLogger(__name__)


def load_seen_cases() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text())
        return set(data)
    except Exception as e:
        logger.warning(f"Could not load seen_cases.json: {e}")
        return set()


def save_seen_cases(case_numbers: set) -> None:
    try:
        SEEN_FILE.write_text(json.dumps(sorted(case_numbers), indent=2))
    except Exception as e:
        logger.error(f"Could not save seen_cases.json: {e}")


def filter_new_cases(listings: list, seen: set) -> list:
    new = [l for l in listings if l["case_number"] not in seen]
    logger.info(f"Dedup: {len(listings)} total, {len(new)} new after filtering {len(seen)} seen")
    return new
