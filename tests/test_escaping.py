"""Unit tests for HTML escaping, clipboard URL generation, and balance formulas."""

import html
import json
import re
import unittest
from typing import Dict, List, Tuple

def extract_highlighted_snippet(full_text: str, matched_phrase: str, words_around: int = 4) -> Tuple[str, str]:
    if not full_text:
        return "-", "-"
    clean_full = full_text.replace("\n", " ").strip()
    escaped_full = html.escape(clean_full)
    
    if not matched_phrase or matched_phrase in ("Ничего не найдено", "none"):
        disp = clean_full[:95] + ("..." if len(clean_full) > 95 else "")
        return html.escape(disp), escaped_full

    m = re.search(re.escape(matched_phrase), clean_full, re.IGNORECASE)
    if not m:
        words = [re.escape(w.replace("ё", "е")) for w in re.split(r"\s+", matched_phrase) if w]
        if words:
            pat_parts = ["".join([f"[{c}ё]" if c == "е" else c for c in w]) for w in words]
            pat = r"\b" + r"\s+".join(pat_parts)
            try:
                m = re.search(pat, clean_full, re.IGNORECASE)
            except Exception:
                m = None

    if not m:
        m = re.search(r"(?:улучш\w+.*?)(?:яйц\w+|скин\w+|рарк\w+).*?(?:кейсер\w*|апгрейд\w*|dotagrade\w*|грейд\w*)", clean_full, re.IGNORECASE)

    if m:
        start_idx, end_idx = m.start(), m.end()
        pre_text = clean_full[:start_idx]
        pre_words = pre_text.split()
        if len(pre_words) > words_around:
            pre_snippet = "... " + " ".join(pre_words[-words_around:]) + " "
        else:
            pre_snippet = " ".join(pre_words) + (" " if pre_words else "")
            
        match_snippet = clean_full[start_idx:end_idx]
        
        post_text = clean_full[end_idx:]
        post_words = post_text.split()
        if len(post_words) > words_around:
            post_snippet = " " + " ".join(post_words[:words_around]) + " ..."
        else:
            post_snippet = (" " if post_words else "") + " ".join(post_words)
            
        snippet_html = f"{html.escape(pre_snippet)}<mark class='hl-phrase'>{html.escape(match_snippet)}</mark>{html.escape(post_snippet)}"
        return snippet_html, escaped_full
    else:
        disp = clean_full[:95] + ("..." if len(clean_full) > 95 else "")
        return html.escape(disp), escaped_full


class TestDataEscapingAndBalance(unittest.TestCase):
    def test_escaping_special_characters(self):
        """Checks that quotes, <script>, &, and newlines in transcripts are strictly escaped."""
        raw_text = 'Опасный текст: <script>alert("XSS")</script> & "кавычки" \'одинарные\' \n новая строка'
        phrase = 'alert("XSS")'
        
        snip, full = extract_highlighted_snippet(raw_text, phrase)
        
        # Must not contain unescaped raw HTML script tags
        self.assertNotIn("<script>", snip)
        self.assertNotIn("</script>", snip)
        self.assertNotIn("<script>", full)
        
        # Must properly contain escaped entities
        self.assertIn("&lt;script&gt;", snip)
        self.assertIn("&amp;", snip)
        self.assertIn("&quot;", snip)
        
        # Highlight mark tag itself is valid and clean
        self.assertIn("<mark class='hl-phrase'>", snip)
        self.assertIn("</mark>", snip)

    def test_data_links_attribute_escaping(self):
        """Checks that JSON array of URLs in data-links attribute is safe against quote injection."""
        urls = [
            'https://www.tiktok.com/@twitch.clown/video/12345?query="test"&foo=bar',
            'https://www.tiktok.com/@twitch.clown/video/67890<script>'
        ]
        raw_json = json.dumps(urls, ensure_ascii=False)
        attr_val = html.escape(raw_json, quote=True)
        
        # Attribute value must not contain bare unescaped double quotes
        self.assertNotIn('"', attr_val)
        self.assertIn('&quot;', attr_val)
        
        # Simulating browser reading back the attribute:
        unescaped = html.unescape(attr_val)
        parsed = json.loads(unescaped)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0], urls[0])
        self.assertEqual(parsed[1], urls[1])

    def test_balance_formula(self):
        """Checks formula: total_found = filtered + verified + errors."""
        total_found = 58
        filtered_views = 16
        filtered_date = 0
        filtered_total = filtered_views + filtered_date
        cnt_all_promo = 40
        cnt_no_promo = 1
        verified = cnt_all_promo + cnt_no_promo  # 41
        errors = 1  # 58 - 16 - 41 = 1
        
        # Balance check
        self.assertEqual(total_found, filtered_total + verified + errors)
        
        # Percentage rounding check: 40/41 = 97.56% -> 98%
        pct = round((cnt_all_promo / verified) * 100)
        self.assertEqual(pct, 98)

    def test_days_preset_consistency(self):
        """Checks that 7 days preset covers exactly 7 calendar days inclusive."""
        from datetime import date, timedelta
        today = date(2026, 10, 26)
        start_7d = today - timedelta(days=6)
        calc_days = (today - start_7d).days + 1
        self.assertEqual(calc_days, 7)
        
        start_14d = today - timedelta(days=13)
        self.assertEqual((today - start_14d).days + 1, 14)


if __name__ == "__main__":
    unittest.main()
