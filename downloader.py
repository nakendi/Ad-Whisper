"""Audio downloader module using yt-dlp and ffmpeg.

Extracts only the audio stream (no video download), converts to 16kHz WAV,
and determines exact duration.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yt_dlp
from curl_cffi import requests as c_req

from database import Database

logger = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def get_ffmpeg_dir() -> Optional[Path]:
    """Finds directory containing ffmpeg executable within project, runtime, or PATH."""
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "bin",
        base_dir / "ffmpeg",
        base_dir / "runtime" / "bin",
        Path(sys.prefix) / "bin",
        Path(sys.prefix) / "Scripts",
    ]
    for c in candidates:
        if (c / "ffmpeg.exe").exists() or (c / "ffmpeg").exists():
            return c
    found = shutil.which("ffmpeg")
    if found:
        return Path(found).parent
    return None

def get_ffmpeg_path() -> str:
    fdir = get_ffmpeg_dir()
    if fdir:
        cand = fdir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if cand.exists():
            return str(cand)
    return "ffmpeg"

def get_ffprobe_path() -> str:
    fdir = get_ffmpeg_dir()
    if fdir:
        cand = fdir / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if cand.exists():
            return str(cand)
    return "ffprobe"

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
            ffprobe_bin = get_ffprobe_path()
            cmd = [
                ffprobe_bin,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path)
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                creationflags=CREATE_NO_WINDOW
            )
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

        f_dir = get_ffmpeg_dir()

        ydl_opts: Dict[str, Any] = {
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

        if f_dir:
            ydl_opts["ffmpeg_location"] = str(f_dir)

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
            logger.warning("Direct yt-dlp download failed for %s (%s): %s. Trying fallback stream...", video_id, url, e)
            if self.download_via_fallback_stream(video_id, target_path):
                duration = self.probe_duration(target_path)
                self.db.update_video_status(video_id, status="downloaded", duration=duration,
                                           local_audio_path=str(target_path))
                return True, str(target_path), duration, None

            err_msg = f"Ошибка скачивания аудио: {e}"
            logger.error("All download methods failed for video %s (%s): %s", video_id, url, e)
            self.db.update_video_status(video_id, status="poor_quality", error_message=err_msg)
            return False, None, 0.0, err_msg

    def download_via_fallback_stream(self, video_id: str, target_path: Path) -> bool:
        """Fallback method: extracts direct CDN media stream from public mirror and downloads via ffmpeg."""
        try:
            logger.info("Attempting fallback direct CDN stream download for %s...", video_id)
            mirror_url = f"https://urlebird.com/video/{video_id}/"
            r = c_req.get(mirror_url, impersonate="chrome124", timeout=12)
            if r.status_code == 200:
                vids = re.findall(r'<video[^>]*src="([^"]+)"', r.text)
                if vids:
                    direct_url = vids[0]
                    ffmpeg_bin = get_ffmpeg_path()
                    cmd = [
                        ffmpeg_bin, "-y",
                        "-i", direct_url,
                        "-vn",
                        "-ar", "16000",
                        "-ac", "1",
                        str(target_path)
                    ]
                    res = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=45,
                        creationflags=CREATE_NO_WINDOW
                    )
                    if res.returncode == 0 and target_path.exists() and target_path.stat().st_size > 1024:
                        logger.info("Fallback CDN stream download succeeded for %s", video_id)
                        return True
        except Exception as e:
            logger.warning("Fallback CDN download failed for %s: %s", video_id, e)
        return False
