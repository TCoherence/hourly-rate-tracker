"""Detect an IANA system timezone without shelling out or requesting privileges."""
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os


def _valid_zone(value):
    if not isinstance(value, str) or not value or len(value) > 80:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return value


def detect_system_timezone():
    """Prefer the OS zone database link; use UTC if no IANA zone is available.

    macOS normally points /etc/localtime at /var/db/timezone/zoneinfo/…;
    Linux commonly points it at /usr/share/zoneinfo/….  A TZ environment
    override is only consulted when those OS settings are unavailable.
    """
    try:
        target = str(Path('/etc/localtime').resolve(strict=True))
        marker = '/zoneinfo/'
        if marker in target:
            zone = _valid_zone(target.rsplit(marker, 1)[1])
            if zone:
                return zone
    except (OSError, RuntimeError):
        pass
    try:
        zone = _valid_zone(Path('/etc/timezone').read_text(encoding='utf-8').strip())
        if zone:
            return zone
    except (OSError, UnicodeError):
        pass
    zone = _valid_zone(os.environ.get('TZ', '').lstrip(':'))
    return zone or 'UTC'
