"""Audio downloader module using yt-dlp and ffmpeg.

Extracts only the audio stream (no video download), converts to 16kHz WAV,
and determines exact duration.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yt_dlp

from database import Database

logger = logging.getLogger(__name__)

class AudioDownloader:
    def __init__(self, db: Database, output_dir: str = "data/temp_audio",
                 cookies_file: Optional[str] = None):
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file

    def get_audio_path_for_video(self, video_id: str) -> Path:
        return self.output_dir / f"{video_id}.wav"

    def probe_duration(self, audio_path: Path) -> float:
        """Determines audio duration in seconds using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path)
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0.0))
            return duration
        except Exception as e:
            logger.warning("Could not probe duration with ffprobe for %s: %s", audio_path, e)
            return 0.0

    def download_audio(self, video_id: str, url: str) -> Tuple[bool, Optional[str], float, Optional[str]]:
        """Downloads only the audio track from TikTok, converts to 16kHz WAV.
        
        Returns:
            (success: bool, audio_path: Optional[str], duration: float, error_message: Optional[str])
        """
        target_path = self.get_audio_path_for_video(video_id)
        
        # If already downloaded, check and return
        if target_path.exists() and target_path.stat().st_size > 1024:
            duration = self.probe_duration(target_path)
            self.db.update_video_status(video_id, status="downloaded", duration=duration,
                                       local_audio_path=str(target_path))
            return True, str(target_path), duration, None

        ydl_opts = {
            "format": "ba/b",  # Prefer audio-only, fallback to video if single stream
            "outtmpl": str(self.output_dir / f"{video_id}.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
            "postprocessor_args": [
                "-ar", "16000",   # 16kHz sample rate optimal for Whisper
                "-ac", "1",       # Mono
            ],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        if self.cookies_file and Path(self.cookies_file).exists():
            ydl_opts["cookiefile"] = self.cookies_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if target_path.exists() and target_path.stat().st_size > 1024:
                duration = self.probe_duration(target_path)
                self.db.update_video_status(video_id, status="downloaded", duration=duration,
                                           local_audio_path=str(target_path))
                return True, str(target_path), duration, None
            else:
                err = "Файл аудио не был создан или имеет нулевой размер"
                self.db.update_video_status(video_id, status="poor_quality", error_message=err)
                return False, None, 0.0, err

        except Exception as e:
            err_msg = f"Ошибка скачивания аудио: {e}"
            logger.error("Download failed for video %s (%s): %s", video_id, url, e)
            self.db.update_video_status(video_id, status="poor_quality", error_message=err_msg)
            return False, None, 0.0, err_msg
