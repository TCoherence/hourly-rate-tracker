"""Conservative continuous overlap tracking, independent of work calculations."""
import secrets


class ScreenAlertTracker:
    """A candidate exists only while successive recent samples are confirmed.

    The tracker is intentionally not restored after a restart: a new process
    cannot know whether the screen slept or woke during its downtime.
    """
    def __init__(self, max_gap=45):
        self.max_gap = max_gap
        self.start = self.last = self.last_mono = None
        self.alert_id = None
        self.saved_end = None
        self.full = False

    def reset(self, alerts):
        changed = False
        if self.alert_id is not None:
            for item in alerts:
                if item['id'] == self.alert_id and self.last is not None and item['end'] != self.last:
                    item['end'] = self.last
                    changed = True
                    break
        self.start = self.last = self.last_mono = None
        self.alert_id = self.saved_end = None
        self.full = False
        return changed

    def observe(self, stamp, monotonic, eligible, threshold_hours, alerts):
        """Mutate the caller's validated alert list; return whether it changed."""
        if not eligible:
            return self.reset(alerts)
        changed = False
        if self.last is not None:
            wall, elapsed = stamp - self.last, monotonic - self.last_mono
            if not (0 <= wall <= self.max_gap and 0 <= elapsed <= self.max_gap and abs(wall - elapsed) <= 2):
                changed = self.reset(alerts)
        if self.start is None:
            self.start = stamp
        self.last, self.last_mono = stamp, monotonic
        if self.alert_id is None and stamp - self.start >= threshold_hours * 3600:
            # Never silently throw away pending reminders to make room.
            if len(alerts) >= 1000:
                kept = next((i for i, item in enumerate(alerts) if item['status'] == 'kept'), None)
                if kept is None:
                    self.full = True
                    return changed
                alerts.pop(kept)
            self.full = False
            self.alert_id = secrets.token_urlsafe(12)
            alerts.append({'id': self.alert_id, 'start': self.start, 'end': stamp, 'status': 'pending'})
            self.saved_end = stamp
            changed = True
        elif self.alert_id is not None and stamp - self.saved_end >= 60:
            for item in alerts:
                if item['id'] == self.alert_id:
                    item['end'] = stamp
                    self.saved_end = stamp
                    changed = True
                    break
        return changed
