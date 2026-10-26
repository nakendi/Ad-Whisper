"""Unit tests for date range filtering requirements."""

import unittest
from datetime import date, datetime, timezone, timedelta
from collector import TikTokCollector
from database import Database

class TestDateFilter(unittest.TestCase):
    def test_snowflake_timestamp_extraction(self):
        # Real TikTok Snowflake IDs
        ts1 = TikTokCollector.extract_snowflake_timestamp("7700682721734954241")
        self.assertIsNotNone(ts1)
        dt1 = datetime.fromtimestamp(ts1, tz=timezone.utc)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 10)
        self.assertEqual(dt1.day, 25)

        # Older video from Oct 17 2026
        ts2 = TikTokCollector.extract_snowflake_timestamp("7697770104985013556")
        self.assertIsNotNone(ts2)
        dt2 = datetime.fromtimestamp(ts2, tz=timezone.utc)
        self.assertEqual(dt2.year, 2026)
        self.assertEqual(dt2.month, 10)
        self.assertEqual(dt2.day, 17)

        # Invalid or non-snowflake IDs
        self.assertIsNone(TikTokCollector.extract_snowflake_timestamp("12345"))
        self.assertIsNone(TikTokCollector.extract_snowflake_timestamp("not_a_number"))

    def test_inclusive_boundaries(self):
        start_date = date(2026, 10, 1)
        end_date = date(2026, 10, 25)

        # Video at start date boundary 00:00:00
        dt_start_boundary = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(TikTokCollector.is_within_date_range(dt_start_boundary, start_date, end_date))

        # Video at end date boundary 23:59:59
        dt_end_boundary = datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc)
        self.assertTrue(TikTokCollector.is_within_date_range(dt_end_boundary, start_date, end_date))

        # Video in between
        dt_mid = datetime(2026, 10, 15, 14, 30, 0, tzinfo=timezone.utc)
        self.assertTrue(TikTokCollector.is_within_date_range(dt_mid, start_date, end_date))

        # Video before start
        dt_before = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
        self.assertFalse(TikTokCollector.is_within_date_range(dt_before, start_date, end_date))

        # Video after end
        dt_after = datetime(2026, 10, 26, 0, 0, 1, tzinfo=timezone.utc)
        self.assertFalse(TikTokCollector.is_within_date_range(dt_after, start_date, end_date))

        # Unknown date must return False
        self.assertFalse(TikTokCollector.is_within_date_range(None, start_date, end_date))

    def test_all_time(self):
        dt_random = datetime(2024, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(TikTokCollector.is_within_date_range(dt_random, None, None))
        self.assertTrue(TikTokCollector.is_within_date_range(None, None, None))

    def test_database_date_filtering_multiple_ranges(self):
        # Create a test database in temp directory
        import tempfile, shutil
        from pathlib import Path
        temp_dir = tempfile.mkdtemp()
        try:
            db_path = str(Path(temp_dir) / "test_date_db.db")
            test_db = Database(db_path)

            # Insert 3 videos with distinct dates:
            # Vid A: 2026-10-17
            vid_a = "7697770104985013556"
            ts_a = int(vid_a) >> 32
            dt_a_str = datetime.fromtimestamp(ts_a, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            test_db.save_video(vid_a, f"https://tiktok.com/@u/video/{vid_a}", "u", "Vid A", 5000, dt_a_str, ts_a, status="analyzed")

            # Vid B: 2026-10-21
            ts_b = int(datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc).timestamp())
            vid_b = str((ts_b << 32) + 123456)
            test_db.save_video(vid_b, f"https://tiktok.com/@u/video/{vid_b}", "u", "Vid B", 8000, "2026-10-21 15:00:00", ts_b, status="analyzed")

            # Vid C: 2026-10-25
            vid_c = "7700682721734954241"
            ts_c = int(vid_c) >> 32
            dt_c_str = datetime.fromtimestamp(ts_c, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            test_db.save_video(vid_c, f"https://tiktok.com/@u/video/{vid_c}", "u", "Vid C", 12000, dt_c_str, ts_c, status="analyzed")

            # Range 1: Only Oct 25 (Today) -> Should return ONLY Vid C
            res_today = test_db.get_results_table_data(start_date=date(2026, 10, 25), end_date=date(2026, 10, 25))
            self.assertEqual(len(res_today), 1)
            self.assertEqual(res_today[0]["video_id"], vid_c)

            # Range 2: Oct 20 to Oct 25 -> Should return Vid B and Vid C (NOT Vid A)
            res_week = test_db.get_results_table_data(start_date=date(2026, 10, 20), end_date=date(2026, 10, 25))
            self.assertEqual(len(res_week), 2)
            v_ids = {r["video_id"] for r in res_week}
            self.assertEqual(v_ids, {vid_b, vid_c})

            # Range 3: Oct 15 to Oct 19 -> Should return ONLY Vid A
            res_past = test_db.get_results_table_data(start_date=date(2026, 10, 15), end_date=date(2026, 10, 19))
            self.assertEqual(len(res_past), 1)
            self.assertEqual(res_past[0]["video_id"], vid_a)

            # Range 4: All time (None, None) -> Should return all 3
            res_all = test_db.get_results_table_data(start_date=None, end_date=None)
            self.assertEqual(len(res_all), 3)

            # Summary stats check for Range 2
            stats_week = test_db.get_summary_stats(start_date=date(2026, 10, 20), end_date=date(2026, 10, 25))
            self.assertEqual(stats_week["total_collected"], 2)
            self.assertEqual(stats_week["total_analyzed"], 2)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
