"""Private, revocable browser grants; never store raw browser credentials."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time

LIFETIME = 14 * 24 * 60 * 60
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def _check_regular_private(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise OSError("invalid private authorization file")
    return True


def write_private_json(path, value):
    """Write atomically in the existing private directory, rejecting symlinks."""
    path = Path(path)
    _check_regular_private(path)
    fd, temporary = tempfile.mkstemp(prefix=".hourly-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        _check_regular_private(path)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class BrowserGrants:
    def __init__(self, directory):
        self.path = Path(directory) / "browser-authorizations.json"
        self.lock = threading.RLock()

    def _read(self):
        if not _check_regular_private(self.path):
            return {}
        fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > 131072):
                raise OSError("invalid private authorization file")
            value = json.load(stream)
        if not isinstance(value, dict) or set(value) != {"version", "grants"} or value["version"] != 1 or not isinstance(value["grants"], dict):
            raise ValueError("invalid authorization registry")
        grants = value["grants"]
        if len(grants) > 1000 or any(not isinstance(k, str) or not _DIGEST.fullmatch(k) or type(v) not in (int, float) or not math.isfinite(v) for k, v in grants.items()):
            raise ValueError("invalid authorization registry")
        return grants

    def _write(self, grants):
        write_private_json(self.path, {"version": 1, "grants": grants})

    def issue(self):
        now = time.time()
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self.lock:
            grants = {k: v for k, v in self._read().items() if v > now}
            if len(grants) >= 1000:
                raise ValueError("too many authorizations")
            expiry = int(now + LIFETIME)
            grants[digest] = expiry
            self._write(grants)
        return token, expiry

    def verify(self, token):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            return False
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        try:
            with self.lock:
                expiry = self._read().get(digest, 0)
            return expiry > time.time()
        except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeError):
            return False

    def extend(self, token):
        """Extend this active browser's grant, without accepting a session cookie."""
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            return None
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self.lock:
            grants = self._read()
            now = time.time()
            old_expiry = grants.get(digest, 0)
            if old_expiry <= now:
                return None
            expiry = max(old_expiry, int(now + LIFETIME))
            grants[digest] = expiry
            self._write(grants)
            return expiry

    def clear(self):
        with self.lock:
            self._write({})
