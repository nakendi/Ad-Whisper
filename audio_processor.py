"""Audio preprocessing, VAD management, and Demucs vocal separation module.

Improves speech recognition accuracy in high-noise, loud-music, and multi-speaker TikTok environments.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, demucs_output_dir: str = "data/demucs_audio", device: str = "cuda"):
        self.demucs_output_dir = Path(demucs_output_dir)
        self.demucs_output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device

    def preprocess_audio(self, input_path: str, output_path: Optional[str] = None) -> str:
        """Preprocesses audio using ffmpeg:
        - High-pass filter at 80Hz (cuts subwoofer rumble and traffic noise)
        - Dynamic audio normalizer (dynaudnorm) to boost quiet whispered speech while preventing clipping
        - 16 kHz sample rate, mono channel (Whisper standard)
        """
        inp = Path(input_path)
        if not inp.exists():
            raise FileNotFoundError(f"Audio file not found: {input_path}")

        if not output_path:
            output_path = str(inp.parent / f"{inp.stem}_norm.wav")
        out = Path(output_path)

        if out.exists() and out.stat().st_size > 1024:
            return str(out)

        # ffmpeg audio filter:
        # highpass=f=80, dynaudnorm=f=150:g=15:m=10.0:r=0.9:b=1
        filter_str = "highpass=f=80,dynaudnorm=f=150:g=15:m=10.0:r=0.9:b=1"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(inp),
            "-af", filter_str,
            "-ar", "16000",
            "-ac", "1",
            str(out)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and out.exists() and out.stat().st_size > 1024:
                logger.info("Audio preprocessed successfully: %s", out)
                return str(out)
            else:
                logger.warning("ffmpeg dynaudnorm filter failed, using original: %s", res.stderr)
                return str(inp)
        except Exception as e:
            logger.warning("Error running ffmpeg normalization: %s", e)
            return str(inp)

    def separate_vocals_with_demucs(self, input_path: str, video_id: str) -> Optional[str]:
        """Separates vocals from background music/sfx using Meta's Demucs (htdemucs).
        
        Returns the path to the isolated vocals WAV file.
        """
        inp = Path(input_path)
        if not inp.exists():
            logger.error("File does not exist: %s", input_path)
            return None

        vocals_target = self.demucs_output_dir / f"{video_id}_vocals.wav"
        if vocals_target.exists() and vocals_target.stat().st_size > 1024:
            return str(vocals_target)

        logger.info("Running Demucs vocal separation on %s (device: %s)...", inp.name, self.device)

        # Run demucs as python module
        # python -m demucs --two-stems vocals -n htdemucs -o <output_dir> -d <device> <input_path>
        cmd = [
            sys.executable,
            "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", str(self.demucs_output_dir),
            "-d", self.device,
            str(inp)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            expected_demucs_vocals = self.demucs_output_dir / "htdemucs" / inp.stem / "vocals.wav"

            # Fallback to CPU if CUDA execution failed (e.g. OutOfMemory)
            if not expected_demucs_vocals.exists() and self.device == "cuda":
                logger.warning("Demucs CUDA execution failed or ran out of memory (%s). Retrying on CPU...", res.stderr[:200])
                cmd_cpu = [
                    sys.executable,
                    "-m", "demucs",
                    "--two-stems", "vocals",
                    "-n", "htdemucs",
                    "-o", str(self.demucs_output_dir),
                    "-d", "cpu",
                    str(inp)
                ]
                subprocess.run(cmd_cpu, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Demucs places files in <output_dir>/htdemucs/<stem>/vocals.wav
            if expected_demucs_vocals.exists():
                # Convert/copy to 16kHz mono wav at vocals_target
                conv_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(expected_demucs_vocals),
                    "-ar", "16000",
                    "-ac", "1",
                    str(vocals_target)
                ]
                subprocess.run(conv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Cleanup raw demucs intermediate directory
                try:
                    shutil.rmtree(self.demucs_output_dir / "htdemucs" / inp.stem, ignore_errors=True)
                except Exception:
                    pass

                if vocals_target.exists():
                    logger.info("Demucs vocal extraction complete: %s", vocals_target)
                    return str(vocals_target)

            logger.warning("Demucs did not produce expected output file: %s. Stderr: %s",
                           expected_demucs_vocals, res.stderr[:300])
            return None

        except Exception as e:
            logger.error("Demucs separation failed for %s: %s", input_path, e)
            return None
