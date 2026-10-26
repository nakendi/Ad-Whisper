"""Unit tests for SQLite Database operations."""

import unittest
from pathlib import Path
import tempfile
import shutil

from database import Database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_scanner.db"
        self.db = Database(str(self.db_path))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_video_insert_and_duplicate(self):
        is_new = self.db.save_video(
            video_id="7100000001",
            url="https://www.tiktok.com/@twitch.clown/video/7100000001",
            author="twitch.clown",
            title="Clip 1",
            views=5000,
            upload_date="2026-10-15 12:00:00",
            upload_timestamp=1792065600,
            status="pending"
        )
        self.assertTrue(is_new)

        # Duplicate save should return False (not new) and update views
        is_new_dup = self.db.save_video(
            video_id="7100000001",
            url="https://www.tiktok.com/@twitch.clown/video/7100000001",
            author="twitch.clown",
            title="Clip 1",
            views=6200,
            upload_date="2026-10-15 12:00:00",
            upload_timestamp=1792065600
        )
        self.assertFalse(is_new_dup)

        video = self.db.get_video("7100000001")
        self.assertIsNotNone(video)
        self.assertEqual(video["views"], 6200)

    def test_save_match_and_summary(self):
        vid_id = "7100000002"
        self.db.save_video(
            video_id=vid_id,
            url=f"https://www.tiktok.com/@twitch.clown/video/{vid_id}",
            author="twitch.clown",
            title="Ad Video",
            views=15000,
            upload_date="2026-10-20 18:00:00",
            upload_timestamp=1792519200,
            status="analyzed"
        )

        self.db.save_match(
            video_id=vid_id,
            variant="variant_1",
            matched_phrase="улучшить свое яйцо в баттлпассе кейсера",
            start_time=3.5,
            end_time=6.8,
            timecode_str="00:03 - 00:06",
            confidence=0.95,
            method="exact",
            full_transcription="Всем привет, улучшить свое яйцо в баттлпассе кейсера можно прямо сейчас"
        )

        stats = self.db.get_summary_stats()
        self.assertEqual(stats["variant_1"], 1)
        self.assertEqual(stats["total_analyzed"], 1)

        table_rows = self.db.get_results_table_data()
        self.assertEqual(len(table_rows), 1)
        self.assertEqual(table_rows[0]["variant"], "variant_1")
        self.assertEqual(table_rows[0]["timecode"], "00:03 - 00:06")

    def test_clear_database(self):
        self.db.save_video(
            video_id="7429009999",
            url="https://www.tiktok.com/@twitch.clown/video/7429009999",
            author="twitch.clown",
            title="Test clip",
            views=3000,
            upload_date="2026-10-22 10:00:00",
            upload_timestamp=1792600000,
            status="analyzed"
        )
        self.db.save_video(
            video_id="7700001111",
            url="https://www.tiktok.com/@twitch.clown/video/7700001111",
            author="twitch.clown",
            title="Real clip",
            views=5000,
            upload_date="2026-10-22 10:00:00",
            upload_timestamp=1792600000,
            status="analyzed"
        )
        self.assertEqual(len(self.db.get_all_videos_data()), 2)
        # Clear only test data
        self.db.clear_database(only_test_data=True)
        all_vids = self.db.get_all_videos_data()
        self.assertEqual(len(all_vids), 1)
        self.assertEqual(all_vids[0]["video_id"], "7700001111")
        # Clear all
        self.db.clear_database(only_test_data=False)
        self.assertEqual(len(self.db.get_all_videos_data()), 0)

if __name__ == "__main__":
    unittest.main()
