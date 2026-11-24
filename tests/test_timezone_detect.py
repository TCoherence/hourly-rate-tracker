"""Fresh databases capture a safe OS timezone; existing data is unchanged."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from store import Store
from timezone_detect import detect_system_timezone


class TimezoneDetectionTests(TestCase):
    def test_macos_zoneinfo_link_wins_over_environment(self):
        with patch('timezone_detect.Path.resolve', return_value=Path('/var/db/timezone/zoneinfo/Asia/Tokyo')):
            with patch.dict('os.environ', {'TZ': 'Europe/London'}):
                self.assertEqual(detect_system_timezone(), 'Asia/Tokyo')

    def test_invalid_system_data_and_environment_fallback_to_utc(self):
        with patch('timezone_detect.Path.resolve', return_value=Path('/invalid/zoneinfo/Definitely/NotAZone')):
            with patch('timezone_detect.Path.read_text', return_value='Also/Invalid'):
                with patch.dict('os.environ', {'TZ': 'No/Such_Zone'}):
                    self.assertEqual(detect_system_timezone(), 'UTC')

    def test_environment_zone_is_only_used_as_last_fallback(self):
        with patch('timezone_detect.Path.resolve', side_effect=OSError):
            with patch('timezone_detect.Path.read_text', side_effect=OSError):
                with patch.dict('os.environ', {'TZ': 'Europe/London'}):
                    self.assertEqual(detect_system_timezone(), 'Europe/London')

    def test_new_database_timezone_is_persisted_and_does_not_follow_changes(self):
        with TemporaryDirectory() as directory:
            with patch('store.detect_system_timezone', return_value='Asia/Tokyo'):
                db = Store(directory)
                self.assertEqual(db.settings()['timezone'], 'Asia/Tokyo')
                db.close()
            with patch('store.detect_system_timezone', return_value='Europe/London'):
                db = Store(directory)
                self.assertEqual(db.settings()['timezone'], 'Asia/Tokyo')
                db.save_settings({'timezone': 'America/New_York'})
                db.close()
            with patch('store.detect_system_timezone', return_value='UTC'):
                db = Store(directory)
                self.assertEqual(db.settings()['timezone'], 'America/New_York')
                db.close()

    def test_legacy_database_without_saved_settings_keeps_old_default(self):
        with TemporaryDirectory() as directory:
            with sqlite3.connect(Path(directory) / 'records.sqlite3'):
                pass
            with patch('store.detect_system_timezone', return_value='Asia/Tokyo'):
                db = Store(directory)
                self.assertEqual(db.settings()['timezone'], 'America/Los_Angeles')
                db.close()
