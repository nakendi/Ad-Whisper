"""Core Scanner Engine that orchestrates:
- Video post collection & filtering
- Audio extraction & normalization
- Speech recognition via faster-whisper
- Multi-stage matching & Demucs vocal separation
- Database persistence and results aggregation
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from audio_processor import AudioProcessor
from collector import TikTokCollector
from config import load_config
from database import Database
from downloader import AudioDownloader
from exporter import ReportExporter
from matcher import MatchResult, PhraseMatcher
from transcriber import SpeechTranscriber

logger = logging.getLogger(__name__)

class ScannerEngine:
    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        
        db_path = self.config.get("storage", {}).get("db_path", "data/scanner.db")
        self.db = Database(db_path)

        self.audio_processor = AudioProcessor(
            demucs_output_dir=self.config.get("storage", {}).get("demucs_output_dir", "data/demucs_audio"),
            device=self.config.get("demucs", {}).get("device", "cuda")
        )

        self.downloader = AudioDownloader(
            db=self.db,
            output_dir=self.config.get("storage", {}).get("temp_audio_dir", "data/temp_audio")
        )

        self.collector = TikTokCollector(db=self.db)
        
        # Matcher
        match_cfg = self.config.get("matching", {})
        self.matcher = PhraseMatcher(
            exact_threshold=match_cfg.get("exact_threshold", 0.95),
            fuzzy_threshold=match_cfg.get("fuzzy_threshold", 0.72),
            doubtful_lower=match_cfg.get("doubtful_lower_bound", 0.45),
            doubtful_upper=match_cfg.get("doubtful_upper_bound", 0.74)
        )

        self.exporter = ReportExporter(
            db=self.db,
            export_dir=self.config.get("storage", {}).get("export_dir", "data/exports")
        )

        self._transcriber: Optional[SpeechTranscriber] = None

    @property
    def transcriber(self) -> SpeechTranscriber:
        """Lazy loader for speech transcriber model."""
        if self._transcriber is None:
            w_cfg = self.config.get("whisper", {})
            self._transcriber = SpeechTranscriber(
                model_name=w_cfg.get("model_name", "large-v3"),
                device=w_cfg.get("device", "cuda"),
                compute_type=w_cfg.get("compute_type", "float16"),
                initial_prompt=w_cfg.get("initial_prompt"),
                vad_filter=w_cfg.get("vad_filter", True),
                vad_parameters=w_cfg.get("vad_parameters")
            )
        return self._transcriber

    def run_scan(self,
                 channel_url: str = "https://www.tiktok.com/@twitch.clown",
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None,
                 min_views: int = 2000,
                 custom_urls: Optional[List[str]] = None,
                 num_threads: int = 3,
                 progress_callback: Optional[Callable[[str, float], None]] = None
                 ) -> Dict[str, Any]:
        """Executes full scan pipeline with configurable parallel processing threads."""
        is_all_time = (start_date is None and end_date is None)
        account = "twitch.clown"

        scan_id = self.db.create_scan(
            account=account,
            start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
            end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
            is_all_time=is_all_time,
            min_views=min_views
        )

        def report(msg: str, pct: float):
            if progress_callback:
                progress_callback(msg, pct)
            logger.info("[%d%%] %s", int(pct * 100), msg)

        report("Сбор публикаций...", 0.05)

        def col_progress(msg: str, curr: int, total: int):
            pct = 0.05 + 0.10 * (curr / max(1, total))
            report(msg, pct)

        # Step 1: Collect videos
        if custom_urls:
            collect_res = self.collector.collect_from_urls(
                urls=custom_urls,
                start_date=start_date,
                end_date=end_date,
                min_views=min_views,
                progress_callback=col_progress
            )
        else:
            collect_res = self.collector.collect_from_channel(
                channel_url=channel_url,
                start_date=start_date,
                end_date=end_date,
                min_views=min_views,
                progress_callback=col_progress
            )

        self.db.update_scan_progress(
            scan_id=scan_id,
            total_found=collect_res.get("total_found", 0),
            filtered_views=collect_res.get("filtered_views_count", 0),
            filtered_dates=collect_res.get("filtered_date_count", 0)
        )

        if not collect_res["success"] and not collect_res["passed_filter"]:
            err_msg = collect_res.get("error_message") or "Не удалось получить публикации."
            self.db.update_scan_progress(scan_id=scan_id, status="failed", error_message=err_msg)
            return {
                "scan_id": scan_id,
                "success": False,
                "error_message": err_msg,
                "waf_blocked": collect_res.get("waf_blocked", False),
                "stats": self.db.get_summary_stats()
            }

        passed_videos = collect_res["passed_filter"]
        total_to_process = len(passed_videos)
        processed_count = 0

        import concurrent.futures

        workers_cnt = max(1, min(int(num_threads), 5))
        if workers_cnt > 1:
            report(f"Найдено подходящих видео: {total_to_process}. Запуск параллельной обработки ({workers_cnt} потока)...", 0.15)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers_cnt) as executor:
                future_to_video = {
                    executor.submit(self.process_video, vid_id=v["id"], url=v["url"]): v
                    for v in passed_videos
                }
                for future in concurrent.futures.as_completed(future_to_video):
                    v = future_to_video[future]
                    processed_count += 1
                    curr_pct = 0.15 + (0.80 * (processed_count / max(1, total_to_process)))
                    report(f"Обработано {processed_count}/{total_to_process} (видео {v['id']})...", curr_pct)
                    self.db.update_scan_progress(scan_id=scan_id, processed=processed_count)
                    try:
                        future.result()
                    except Exception as err:
                        logger.error(f"Ошибка при обработке {v.get('id')}: {err}")
        else:
            report(f"Найдено подходящих видео: {total_to_process}. Запуск последовательной обработки...", 0.15)
            for v in passed_videos:
                self.process_video(vid_id=v["id"], url=v["url"])
                processed_count += 1
                curr_pct = 0.15 + (0.80 * (processed_count / max(1, total_to_process)))
                report(f"Обработано {processed_count}/{total_to_process} (видео {v['id']})...", curr_pct)
                self.db.update_scan_progress(scan_id=scan_id, processed=processed_count)

        report("Формирование отчётов...", 0.96)
        excel_path = self.exporter.export_excel(start_date=start_date, end_date=end_date)
        csv_path = self.exporter.export_csv(start_date=start_date, end_date=end_date)

        self.db.update_scan_progress(scan_id=scan_id, status="completed", processed=processed_count)
        report("Сканирование успешно завершено!", 1.0)

        return {
            "scan_id": scan_id,
            "success": True,
            "total_processed": processed_count,
            "excel_path": str(excel_path),
            "csv_path": str(csv_path),
            "stats": self.db.get_summary_stats(start_date=start_date, end_date=end_date)
        }

    def process_video(self, vid_id: str, url: str,
                      progress_callback: Optional[Callable[[str, float], None]] = None) -> MatchResult:
        """Processes a single video: downloads audio, normalizes, transcribes, matches phrases,
        and triggers Demucs if doubtful. Skips if already analyzed.
        """
        # Check if already processed
        existing = self.db.get_video(vid_id)
        if existing and existing.get("status") == "analyzed":
            logger.info("Video %s already analyzed, skipping re-download and re-transcription.", vid_id)
            return MatchResult(
                found=True,
                variant=existing.get("status"),
                variant_name="Ранее обработано",
                matched_phrase="",
                start_time=0.0,
                end_time=0.0,
                timecode_str="-",
                confidence=1.0,
                method="cached",
                is_doubtful=False,
                verification_notes="Загружено из кэша базы данных"
            )

        # Step A: Download audio stream
        success, audio_path, duration, err = self.downloader.download_audio(video_id=vid_id, url=url)
        if not success or not audio_path:
            return MatchResult(
                found=False,
                variant="none",
                variant_name="Ошибка аудио",
                matched_phrase="",
                start_time=0.0,
                end_time=0.0,
                timecode_str="-",
                confidence=0.0,
                method="error",
                is_doubtful=False,
                verification_notes=err or "Не удалось загрузить аудио"
            )

        # Step B: Audio preprocessing (highpass + dynamic normalization for quiet voice boost)
        clean_audio = self.audio_processor.preprocess_audio(audio_path)

        # Step C: Speech recognition
        try:
            trans_result = self.transcriber.transcribe(clean_audio)
        except Exception as e:
            logger.error("Transcription error on %s: %s", vid_id, e)
            self.db.update_video_status(vid_id, status="error", error_message=f"Ошибка транскрипции: {e}")
            return MatchResult(
                found=False,
                variant="none",
                variant_name="Ошибка транскрипции",
                matched_phrase="",
                start_time=0.0,
                end_time=0.0,
                timecode_str="-",
                confidence=0.0,
                method="error",
                is_doubtful=False,
                verification_notes=str(e)
            )

        full_text = trans_result["full_text"]
        segments = trans_result["segments"]

        self.db.save_transcription(
            video_id=vid_id,
            audio_type="original",
            full_text=full_text,
            segments=segments,
            language=trans_result["language"],
            language_probability=trans_result["language_probability"]
        )

        # Step D: Multi-stage Phrase Matching
        match_res = self.matcher.find_matches_in_text(full_text=full_text, segments=segments)

        # Step E: If match is doubtful (or noisy/low confidence between 45% and 74%),
        # trigger Demucs vocal isolation to re-transcribe isolated vocals!
        if match_res.is_doubtful:
            logger.info("Match for video %s is doubtful (conf=%.2f). Running Demucs separation...",
                        vid_id, match_res.confidence)
            vocals_path = self.audio_processor.separate_vocals_with_demucs(audio_path, video_id=vid_id)
            if vocals_path:
                try:
                    demucs_trans = self.transcriber.transcribe(vocals_path)
                    self.db.save_transcription(
                        video_id=vid_id,
                        audio_type="demucs_vocals",
                        full_text=demucs_trans["full_text"],
                        segments=demucs_trans["segments"],
                        language=demucs_trans["language"],
                        language_probability=demucs_trans["language_probability"]
                    )
                    demucs_match = self.matcher.find_matches_in_text(
                        full_text=demucs_trans["full_text"],
                        segments=demucs_trans["segments"]
                    )

                    # Comparison of multiple transcription results
                    if demucs_match.confidence > match_res.confidence:
                        match_res = demucs_match
                        match_res.verification_notes += " [Подтверждено через Demucs]"
                    elif demucs_match.confidence < 0.35 and match_res.confidence < 0.55:
                        # Demucs proved original was background music illusion
                        match_res.found = False
                        match_res.variant = "none"
                        match_res.confidence = 0.15
                        match_res.verification_notes = "Ложное срабатывание шума, опровергнуто Demucs"

                except Exception as e:
                    logger.warning("Demucs re-transcription failed for %s: %s", vid_id, e)

        # Step F: Persist final match result in SQLite
        self.db.save_match(
            video_id=vid_id,
            variant=match_res.variant,
            matched_phrase=match_res.matched_phrase,
            start_time=match_res.start_time,
            end_time=match_res.end_time,
            timecode_str=match_res.timecode_str,
            confidence=match_res.confidence,
            method=match_res.method,
            full_transcription=full_text,
            is_doubtful=match_res.is_doubtful,
            reprocessed_with_demucs=1 if match_res.is_doubtful else 0,
            verification_notes=match_res.verification_notes
        )

        self.db.update_video_status(vid_id, status="analyzed")

        # Auto-cleanup non-promotional temp audio (saves 80-90% of disk space)
        if self.config.get("auto_cleanup_temp_audio", True):
            if not match_res.found and not match_res.is_doubtful:
                try:
                    for f_to_del in [audio_path, clean_audio]:
                        if f_to_del:
                            p_del = Path(f_to_del)
                            if p_del.exists():
                                p_del.unlink(missing_ok=True)
                except Exception as del_err:
                    logger.debug("Failed to auto-clean temp audio for %s: %s", vid_id, del_err)

        return match_res

    def process_local_audio_file(self, file_path: str, video_id: str,
                                 url: Optional[str] = None,
                                 views: int = 5000,
                                 upload_date: Optional[str] = None) -> MatchResult:
        """Processes a locally provided audio file directly through the AI pipeline."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Local audio file not found: {file_path}")

        if not url:
            url = f"https://www.tiktok.com/@twitch.clown/video/{video_id}"
        if not upload_date:
            upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        duration = self.downloader.probe_duration(p)
        self.db.save_video(
            video_id=video_id,
            url=url,
            author="twitch.clown",
            title=p.stem,
            views=views,
            upload_date=upload_date,
            upload_timestamp=int(datetime.now().timestamp()),
            status="downloaded"
        )
        self.db.update_video_status(video_id, status="downloaded", duration=duration,
                                    local_audio_path=str(p))

        # Audio preprocessing
        clean_audio = self.audio_processor.preprocess_audio(str(p))

        # Whisper Transcription
        trans_result = self.transcriber.transcribe(clean_audio)
        full_text = trans_result["full_text"]
        segments = trans_result["segments"]

        self.db.save_transcription(
            video_id=video_id,
            audio_type="original",
            full_text=full_text,
            segments=segments,
            language=trans_result["language"],
            language_probability=trans_result["language_probability"]
        )

        # Multi-stage Phrase Matching
        match_res = self.matcher.find_matches_in_text(full_text=full_text, segments=segments)

        # Demucs if doubtful
        if match_res.is_doubtful:
            logger.info("Match for %s is doubtful (conf=%.2f). Running Demucs...", video_id, match_res.confidence)
            vocals_path = self.audio_processor.separate_vocals_with_demucs(str(p), video_id=video_id)
            if vocals_path:
                try:
                    demucs_trans = self.transcriber.transcribe(vocals_path)
                    self.db.save_transcription(
                        video_id=video_id,
                        audio_type="demucs_vocals",
                        full_text=demucs_trans["full_text"],
                        segments=demucs_trans["segments"],
                        language=demucs_trans["language"],
                        language_probability=demucs_trans["language_probability"]
                    )
                    demucs_match = self.matcher.find_matches_in_text(
                        full_text=demucs_trans["full_text"],
                        segments=demucs_trans["segments"]
                    )
                    if demucs_match.confidence > match_res.confidence:
                        match_res = demucs_match
                        match_res.verification_notes += " [Подтверждено через Demucs]"
                except Exception as e:
                    logger.warning("Demucs re-transcription failed for %s: %s", video_id, e)

        self.db.save_match(
            video_id=video_id,
            variant=match_res.variant,
            matched_phrase=match_res.matched_phrase,
            start_time=match_res.start_time,
            end_time=match_res.end_time,
            timecode_str=match_res.timecode_str,
            confidence=match_res.confidence,
            method=match_res.method,
            full_transcription=full_text,
            is_doubtful=match_res.is_doubtful,
            reprocessed_with_demucs=1 if match_res.is_doubtful else 0,
            verification_notes=match_res.verification_notes
        )

        self.db.update_video_status(video_id, status="analyzed")
        return match_res

    def reprocess_video_with_demucs(self, vid_id: str) -> MatchResult:
        """Forces Demucs vocal isolation, re-transcription, and re-evaluation for a specific video."""
        video = self.db.get_video(vid_id)
        if not video:
            raise ValueError(f"Video {vid_id} not found in database.")

        audio_path = video.get("local_audio_path")
        if not audio_path or not Path(audio_path).exists():
            success, audio_path, _, err = self.downloader.download_audio(video_id=vid_id, url=video["url"])
            if not success:
                raise RuntimeError(err or "Failed to download audio for reprocessing.")

        vocals_path = self.audio_processor.separate_vocals_with_demucs(audio_path, video_id=vid_id)
        if not vocals_path:
            raise RuntimeError("Demucs failed to separate vocals.")

        trans_result = self.transcriber.transcribe(vocals_path)
        self.db.save_transcription(
            video_id=vid_id,
            audio_type="demucs_vocals",
            full_text=trans_result["full_text"],
            segments=trans_result["segments"],
            language=trans_result["language"],
            language_probability=trans_result["language_probability"]
        )

        match_res = self.matcher.find_matches_in_text(
            full_text=trans_result["full_text"],
            segments=trans_result["segments"]
        )

        self.db.save_match(
            video_id=vid_id,
            variant=match_res.variant,
            matched_phrase=match_res.matched_phrase,
            start_time=match_res.start_time,
            end_time=match_res.end_time,
            timecode_str=match_res.timecode_str,
            confidence=match_res.confidence,
            method=f"{match_res.method}_demucs_forced",
            full_transcription=trans_result["full_text"],
            is_doubtful=match_res.is_doubtful,
            reprocessed_with_demucs=True,
            verification_notes="Принудительное разделение Demucs и повторный анализ"
        )

        return match_res
