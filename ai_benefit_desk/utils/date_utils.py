from datetime import datetime, date, timedelta
from typing import Optional

def today_str() -> str:
    """Return today date in YYYY-MM-DD format."""
    return date.today().isoformat()

def parse_date(d_str: Optional[str]) -> Optional[date]:
    """Safely parse YYYY-MM-DD date string."""
    if not d_str or d_str.upper() == "UNKNOWN":
        return None
    try:
        return datetime.strptime(d_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return None

def is_valid_date_or_unknown(d_str: Optional[str]) -> bool:
    """Check if string is either UNKNOWN or valid YYYY-MM-DD."""
    if d_str is None:
        return False
    if d_str.upper() == "UNKNOWN":
        return True
    try:
        datetime.strptime(d_str.strip(), "%Y-%m-%d")
        return True
    except Exception:
        return False

def is_expired(end_date_str: Optional[str], ref_date: Optional[date] = None) -> bool:
    """Check if end_date is before ref_date (default today)."""
    d = parse_date(end_date_str)
    if not d:
        return False
    today = ref_date or date.today()
    return d < today

def is_expiring_soon(end_date_str: Optional[str], days: int = 7, ref_date: Optional[date] = None) -> bool:
    """Check if end_date is between ref_date and ref_date + days."""
    d = parse_date(end_date_str)
    if not d:
        return False
    today = ref_date or date.today()
    return today <= d <= (today + timedelta(days=days))

def is_review_due(next_review_date_str: Optional[str], ref_date: Optional[date] = None) -> bool:
    """Check if next_review_date is on or before ref_date (default today)."""
    d = parse_date(next_review_date_str)
    if not d:
        return False
    today = ref_date or date.today()
    return d <= today

def is_valid_timezone_iso8601(ts_str: Optional[str]) -> bool:
    """Check if string is a valid timezone-aware ISO8601 datetime (e.g. 2026-08-18T19:00:00+08:00 or 2026-08-18T19:00:00Z)."""
    if not ts_str or not isinstance(ts_str, str):
        return False
    val = ts_str.strip()
    if "T" not in val and "t" not in val:
        return False
    if val.endswith("Z") or val.endswith("z"):
        val = val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val)
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except Exception:
        return False

def now_timezone_iso() -> str:
    """Return current datetime in ISO8601 format with local timezone offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")
