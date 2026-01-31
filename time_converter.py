"""
time_converter.py - Timestamp conversion utilities
"""

from datetime import datetime, timezone
import pytz

VIENNA_TZ = pytz.timezone('Europe/Vienna')

def timestamp_to_vienna_str(timestamp_ms: int) -> str:
    timestamp_sec = timestamp_ms / 1000.0
    utc_dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
    vienna_dt = utc_dt.astimezone(VIENNA_TZ)
    return vienna_dt.strftime('%Y%m%d_%H%M')

def timestamp_to_vienna_short(timestamp_ms: int) -> str:
    timestamp_sec = timestamp_ms / 1000.0
    utc_dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
    vienna_dt = utc_dt.astimezone(VIENNA_TZ)
    return vienna_dt.strftime('%H:%M')

def vienna_str_to_short(vienna_str: str) -> str:
    if not vienna_str or '_' not in vienna_str:
        return "00:00"
    return vienna_str.split('_')[1][:2] + ":" + vienna_str.split('_')[1][2:]

def vienna_to_timestamp(vienna_str: str) -> int:
    """
    Convert Vienna time string back to Unix timestamp (ms)
    """
    dt = datetime.strptime(vienna_str, '%Y%m%d_%H%M')
    vienna_dt = VIENNA_TZ.localize(dt)
    return int(vienna_dt.timestamp() * 1000)
