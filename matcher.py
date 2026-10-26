"""Intelligent multi-stage phrase detector and classifier.

Implements:
1. Exact normalized matching
2. Sliding window fuzzy matching (Levenshtein / token sort / partial ratio)
3. Semantic structural construction matching (Action + Object + Ability + Platform)
4. Context & Hallucination verification
5. Word-level timestamp extraction
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from config import TARGET_VARIANTS, TargetPhrase

logger = logging.getLogger(__name__)

# Try importing rapidfuzz, fallback to difflib
try:
    from rapidfuzz import fuzz
except ImportError:
    import difflib
    class FuzzFallback:
        @staticmethod
        def ratio(s1: str, s2: str) -> float:
            return difflib.SequenceMatcher(None, s1, s2).ratio() * 100.0
        @staticmethod
        def partial_ratio(s1: str, s2: str) -> float:
            return difflib.SequenceMatcher(None, s1, s2).ratio() * 100.0
        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> float:
            s1_sorted = " ".join(sorted(s1.split()))
            s2_sorted = " ".join(sorted(s2.split()))
            return difflib.SequenceMatcher(None, s1_sorted, s2_sorted).ratio() * 100.0
    fuzz = FuzzFallback()

@dataclass
class MatchResult:
    found: bool
    variant: str  # 'variant_1', 'variant_2', 'variant_3', 'none'
    variant_name: str
    matched_phrase: str
    start_time: float
    end_time: float
    timecode_str: str
    confidence: float  # 0.0 to 1.0
    method: str  # 'exact', 'fuzzy', 'semantic', 'llm'
    is_doubtful: bool
    verification_notes: str

class PhraseMatcher:
    def __init__(self, exact_threshold: float = 0.95,
                 fuzzy_threshold: float = 0.72,
                 doubtful_lower: float = 0.45,
                 doubtful_upper: float = 0.74):
        self.exact_threshold = exact_threshold
        self.fuzzy_threshold = fuzzy_threshold
        self.doubtful_lower = doubtful_lower
        self.doubtful_upper = doubtful_upper

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalizes text by lowercasing, replacing ё with е, and removing punctuation."""
        if not text:
            return ""
        t = text.lower().replace("ё", "е")
        # Replace punctuation with spaces
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def format_timecode(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def find_matches_in_text(self, full_text: str, segments: List[Dict[str, Any]]) -> MatchResult:
        """Runs the multi-stage matching pipeline on transcription text and segments."""
        if not full_text or not segments:
            return MatchResult(
                found=False,
                variant="none",
                variant_name="Ничего не найдено",
                matched_phrase="",
                start_time=0.0,
                end_time=0.0,
                timecode_str="00:00 - 00:00",
                confidence=0.0,
                method="none",
                is_doubtful=False,
                verification_notes="Текст транскрипции пуст"
            )

        norm_full = self.normalize_text(full_text)

        best_result: Optional[MatchResult] = None
        best_score = 0.0

        for var_id, var_obj in TARGET_VARIANTS.items():
            res = self._evaluate_variant(var_obj, full_text, norm_full, segments)
            if res.found and res.confidence > best_score:
                best_score = res.confidence
                best_result = res

        if best_result and best_result.confidence >= self.doubtful_lower:
            return best_result

        return MatchResult(
            found=False,
            variant="none",
            variant_name="Ничего не найдено",
            matched_phrase="",
            start_time=0.0,
            end_time=0.0,
            timecode_str="00:00 - 00:00",
            confidence=0.0,
            method="none",
            is_doubtful=False,
            verification_notes="Целевые рекламные конструкции не обнаружены"
        )

    def _evaluate_variant(self, var_obj: TargetPhrase, full_text: str,
                          norm_full: str, segments: List[Dict[str, Any]]) -> MatchResult:
        """Evaluates transcription against a specific target phrase variant."""
        norm_target = self.normalize_text(var_obj.original_phrase)

        # Stage 1: Exact / Regex Matching
        for pattern in var_obj.regex_patterns:
            m = re.search(pattern, norm_full, re.IGNORECASE)
            if m:
                matched_snippet = m.group(0)
                start_t, end_t = self._locate_segment_time(matched_snippet, segments)
                
                # Real fuzzy ratio comparison between spoken phrase and canonical target phrase
                norm_snip = self.normalize_text(matched_snippet)
                r_ratio = fuzz.ratio(norm_target, norm_snip)
                r_token = fuzz.token_sort_ratio(norm_target, norm_snip)
                calc_conf = round(min(0.995, max(0.80, (0.65 * r_ratio + 0.35 * r_token) / 100.0)), 3)

                return MatchResult(
                    found=True,
                    variant=var_obj.id,
                    variant_name=var_obj.name,
                    matched_phrase=matched_snippet,
                    start_time=start_t,
                    end_time=end_t,
                    timecode_str=f"{self.format_timecode(start_t)} - {self.format_timecode(end_t)}",
                    confidence=calc_conf,
                    method="exact_regex",
                    is_doubtful=False,
                    verification_notes="Точное совпадение регулярного выражения конструкции"
                )

        # Stage 2: Sliding Window Fuzzy Matching over Segments
        best_fuzzy_score = 0.0
        best_fuzzy_seg = None
        best_fuzzy_text = ""

        # Flatten segments or group adjacent segments to cover multi-segment phrases
        window_sizes = [1, 2, 3]
        for w_size in window_sizes:
            for i in range(len(segments) - w_size + 1):
                win_segs = segments[i:i + w_size]
                combined_text = " ".join(s.get("text", "") for s in win_segs)
                norm_win = self.normalize_text(combined_text)

                if not norm_win:
                    continue

                # Fuzzy metrics
                token_sort = fuzz.token_sort_ratio(norm_target, norm_win) / 100.0
                partial = fuzz.partial_ratio(norm_target, norm_win) / 100.0
                score = 0.6 * token_sort + 0.4 * partial

                if score > best_fuzzy_score:
                    best_fuzzy_score = score
                    best_fuzzy_seg = win_segs
                    best_fuzzy_text = combined_text

        # Stage 3: Semantic Structural Component Matching
        # Rule: Must have Key Action + Target Object + Target Platform
        # Check components presence in norm_full
        has_action = any(act in norm_full for act in ["улучшить", "улучш", "прокачать", "апнуть", "улучшай"])
        has_object = any(obj in norm_full for obj in var_obj.target_object_keywords)
        has_platform = any(plat in norm_full for plat in var_obj.target_platform_keywords)
        has_modal = any(mod in norm_full for mod in ["можешь", "можете", "можно", "ты можешь"])

        structural_score = 0.0
        if has_object and has_platform:
            structural_score = 0.70
            if has_action:
                structural_score += 0.20
            if has_modal:
                structural_score += 0.08
        elif has_object and has_action and ("кейс" in norm_full or "грейд" in norm_full or "апгрейд" in norm_full):
            structural_score = 0.55

        # IMPORTANT: Rule to prevent single word false positives:
        # If only object is present (e.g. just "яйцо" or "скины") without platform, structural score is 0.
        if not has_platform and not (var_obj.id == "variant_2" and "апгрейд" in norm_full):
            if structural_score > 0.4:
                structural_score = 0.2

        # Combine scores
        final_confidence = max(best_fuzzy_score * 0.9, structural_score)
        
        # Penalize if it's purely a single word match
        words_in_full = norm_full.split()
        if len(words_in_full) < 4:
            final_confidence *= 0.5

        if final_confidence >= self.doubtful_lower:
            start_t = 0.0
            end_t = 0.0
            if best_fuzzy_seg:
                start_t = best_fuzzy_seg[0].get("start", 0.0)
                end_t = best_fuzzy_seg[-1].get("end", 0.0)
            elif segments:
                start_t = segments[0].get("start", 0.0)
                end_t = segments[-1].get("end", 0.0)

            is_doubtful = (final_confidence < self.doubtful_upper)
            method = "semantic" if structural_score >= best_fuzzy_score else "fuzzy"

            return MatchResult(
                found=True,
                variant=var_obj.id,
                variant_name=var_obj.name,
                matched_phrase=best_fuzzy_text or var_obj.original_phrase,
                start_time=start_t,
                end_time=end_t,
                timecode_str=f"{self.format_timecode(start_t)} - {self.format_timecode(end_t)}",
                confidence=round(final_confidence, 2),
                method=method,
                is_doubtful=is_doubtful,
                verification_notes=(
                    f"Обнаружена рекламная конструкция. Действие: {has_action}, "
                    f"Объект: {has_object}, Площадка: {has_platform}. "
                    f"{'Требуется Demucs-проверка' if is_doubtful else 'Высокая уверенность'}"
                )
            )

        return MatchResult(
            found=False,
            variant="none",
            variant_name="Ничего не найдено",
            matched_phrase="",
            start_time=0.0,
            end_time=0.0,
            timecode_str="00:00 - 00:00",
            confidence=round(final_confidence, 2),
            method="none",
            is_doubtful=False,
            verification_notes="Недостаточная уверенность совпадения"
        )

    def _locate_segment_time(self, snippet: str, segments: List[Dict[str, Any]]) -> Tuple[float, float]:
        """Locates the exact start and end time of a snippet within segments."""
        norm_snip = self.normalize_text(snippet)
        snip_words = norm_snip.split()
        if not snip_words:
            return 0.0, 0.0

        for seg in segments:
            seg_norm = self.normalize_text(seg.get("text", ""))
            if snip_words[0] in seg_norm:
                return float(seg.get("start", 0.0)), float(seg.get("end", 0.0))

        # Check word-level timestamps if available
        for seg in segments:
            words = seg.get("words", [])
            for w in words:
                w_norm = self.normalize_text(w.get("word", ""))
                if w_norm == snip_words[0]:
                    start = float(w.get("start", seg.get("start", 0.0)))
                    end = float(seg.get("end", start + 3.0))
                    return start, end

        if segments:
            return float(segments[0].get("start", 0.0)), float(segments[-1].get("end", 0.0))
        return 0.0, 0.0
