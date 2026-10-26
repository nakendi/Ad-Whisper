"""Unit tests for PhraseMatcher and target phrase detection."""

import unittest
from matcher import PhraseMatcher

class TestPhraseMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = PhraseMatcher()

    def test_variant_1_exact(self):
        text = "Всем привет, а улучшить своё яйцо ты можешь в баттлпассе Caser, ссылка в шапке профиля!"
        segments = [{"start": 1.0, "end": 4.5, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_1")
        self.assertGreaterEqual(res.confidence, 0.85)

    def test_variant_1_variations(self):
        # Without "ты", with "батлпасе" (single t), "свое" instead of "своё", cyrillic "кейсера"
        text = "короче улучшить свое яйцо можешь в батлпасе кейсера за пару кликов"
        segments = [{"start": 0.5, "end": 3.8, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_1")
        self.assertGreaterEqual(res.confidence, 0.70)

    def test_variant_2_exact(self):
        text = "А улучшить свои скины ты можешь на Upgrader"
        segments = [{"start": 2.0, "end": 5.0, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_2")
        self.assertGreaterEqual(res.confidence, 0.85)

    def test_variant_2_reordering_and_slight_change(self):
        text = "свои скины ты можешь улучшить на апгрейде прямо сейчас"
        segments = [{"start": 10.0, "end": 14.0, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_2")
        self.assertGreaterEqual(res.confidence, 0.70)

    def test_variant_3_exact(self):
        text = "А улучшить рарки на подарки ты можешь на DotaGrade"
        segments = [{"start": 0.0, "end": 4.0, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_3")
        self.assertGreaterEqual(res.confidence, 0.85)

    def test_variant_3_phonetic_cyrillic(self):
        text = "ты можешь улучшить рарки на подарки на дота дотагрейд"
        segments = [{"start": 1.0, "end": 4.5, "text": text}]
        res = self.matcher.find_matches_in_text(text, segments)
        self.assertTrue(res.found)
        self.assertEqual(res.variant, "variant_3")
        self.assertGreaterEqual(res.confidence, 0.75)

    def test_false_positive_rejection_single_words(self):
        # Case A: Casual mention of egg (food)
        text_egg = "я сегодня утром пожарил себе куриное яйцо с беконом было вкусно"
        segments = [{"start": 0.0, "end": 5.0, "text": text_egg}]
        res_egg = self.matcher.find_matches_in_text(text_egg, segments)
        self.assertFalse(res_egg.found)
        self.assertEqual(res_egg.variant, "none")

        # Case B: Casual mention of skins without upgrade platform
        text_skins = "посмотри какие красивые скины на оружие вышли в новом обновлении игры"
        segments = [{"start": 0.0, "end": 5.0, "text": text_skins}]
        res_skins = self.matcher.find_matches_in_text(text_skins, segments)
        self.assertFalse(res_skins.found)
        self.assertEqual(res_skins.variant, "none")

        # Case C: Casual mention of Dota
        text_dota = "мы вчера играли в доту пять часов подряд и проиграли все катки"
        segments = [{"start": 0.0, "end": 5.0, "text": text_dota}]
        res_dota = self.matcher.find_matches_in_text(text_dota, segments)
        self.assertFalse(res_dota.found)
        self.assertEqual(res_dota.variant, "none")

if __name__ == "__main__":
    unittest.main()
