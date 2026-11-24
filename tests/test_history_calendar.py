"""Calendar and heatmap must share the same daily accounting."""
import unittest
from datetime import datetime, date
from unittest.mock import patch
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
from app import Application

ZONE = ZoneInfo('America/Los_Angeles')
NOW = datetime(2037, 11, 12, 22, tzinfo=ZONE).timestamp()

class HistoryCalendarTests(unittest.TestCase):
    def test_current_month_agrees_with_dashboard_and_old_month_is_available(self):
        with TemporaryDirectory() as directory:
            app = Application(directory, detector=lambda _: ('disabled', 'test'))
            try:
                app.store.save_settings({'timezone': str(ZONE), 'annual_salary': 100000})
                app.store.save_manual_entries([
                    {'date':'2037-11-05', 'kind':'daily_total', 'hours':11, 'note':''},
                    {'date':'2037-11-12', 'kind':'intervals', 'intervals':[{'start':'09:00','end':'11:00'}], 'note':''},
                    {'date':'2024-12-15', 'kind':'daily_total', 'hours':8, 'note':''},
                ], now=NOW)
                vpn_start = datetime(2037, 11, 12, 10, tzinfo=ZONE).timestamp()
                for offset in range(0, 3601, 30):
                    app.store.record(vpn_start + offset, 'connected')
                app.store.sync(NOW)
                with patch('app.time.time', return_value=NOW):
                    history = {day['date']: day for day in app.history_month('2037-11')['days']}
                    dashboard = {day['date']: day for day in app.dashboard('month')['summary']['days']}
                    for key in ('work_hours', 'status', 'vpn_work_hours', 'manual_kind'):
                        self.assertEqual(history['2037-11-05'][key], dashboard['2037-11-05'][key])
                        self.assertEqual(history['2037-11-12'][key], dashboard['2037-11-12'][key])
                    self.assertAlmostEqual(history['2037-11-12']['work_hours'], 2)
                    self.assertAlmostEqual(history['2037-11-12']['vpn_work_hours'], 1)
                    self.assertEqual(history['2037-11-20']['status'], 'future')
                    old = app.history_month('2024-12')['days']
                    self.assertEqual(next(x for x in old if x['date']=='2024-12-15')['work_hours'], 8)
                    for invalid in ('2037-13','2037-1','2038-01','garbage'):
                        with self.assertRaises(ValueError): app.history_month(invalid)
            finally:
                app.close()
