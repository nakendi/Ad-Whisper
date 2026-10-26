"""Unit tests for TikTokCollector card extraction and parsing."""

import unittest
from datetime import datetime, timezone, timedelta
from collector import TikTokCollector

class TestTikTokCollector(unittest.TestCase):
    def test_parse_views(self):
        self.assertEqual(TikTokCollector.parse_views_str("137"), 137)
        self.assertEqual(TikTokCollector.parse_views_str("1.87K"), 1870)
        self.assertEqual(TikTokCollector.parse_views_str("59.5K"), 59500)
        self.assertEqual(TikTokCollector.parse_views_str("1.2M"), 1200000)
        self.assertEqual(TikTokCollector.parse_views_str(""), 0)

    def test_parse_relative_time(self):
        now = datetime.now(timezone.utc)
        dt_10m = TikTokCollector.parse_relative_time_str("10 minutes ago")
        self.assertTrue(abs((now - dt_10m).total_seconds() - 600) < 5)

        dt_2h = TikTokCollector.parse_relative_time_str("2 hours ago")
        self.assertTrue(abs((now - dt_2h).total_seconds() - 7200) < 5)

        dt_3d = TikTokCollector.parse_relative_time_str("3 days ago")
        self.assertTrue(abs((now - dt_3d).total_seconds() - 3 * 86400) < 5)

    def test_extract_cards(self):
        sample_html = """
        <div class="thumb wb">
            <div class="stats">
                <div><span><i class="fas fa-clock"></i> 2 hours ago</span></div>
                <div><span><i class="fas fa-play"></i> 14.5K</span></div>
            </div>
            <div class="info3">
                <a href="https://urlebird.com/video/7700123456789012345/"><span>#dota2 #stream</span></a>
            </div>
        </div>
        """
        cards = TikTokCollector.extract_cards_from_html(sample_html, "twitch.clown")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "7700123456789012345")
        self.assertEqual(cards[0]["views"], 14500)
        self.assertEqual(cards[0]["author"], "twitch.clown")
        self.assertIn("#dota2", cards[0]["title"])

if __name__ == "__main__":
    unittest.main()
