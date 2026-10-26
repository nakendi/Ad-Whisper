"""Speech recognition module using faster-whisper (large-v3).

Optimized for RTX 4070 (12GB VRAM):
- Device: CUDA
- Compute type: float16 (with int8 / CPU fallback)
- Word-level timestamps
- Tailored initial prompt for streamer slang and promotional phrases
- VAD configured not to cut quiet speech
"""

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def setup_nvidia_dll_paths() -> None:
    """Discovers and registers NVIDIA CUDA DLL directories (cublas, cudnn) on Windows."""
    if sys.platform != "win32":
        return

    # Check virtual environment and site-packages for nvidia packages
    base_dirs = [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia",
        Path(__file__).resolve().parent / ".venv" / "Lib" / "site-packages" / "nvidia"
    ]

    for b in base_dirs:
        if b.exists():
            for sub in b.iterdir():
                for candidate in [sub / "bin", sub / "lib"]:
                    if candidate.exists():
                        try:
                            os.add_dll_directory(str(candidate))
                            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
                        except Exception as e:
                            logger.debug("Could not add DLL dir %s: %s", candidate, e)

# Run DLL setup prior to faster_whisper import
setup_nvidia_dll_paths()

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

class SpeechTranscriber:
    def __init__(self, model_name: str = "large-v3",
                 device: str = "cuda",
                 compute_type: str = "float16",
                 initial_prompt: Optional[str] = None,
                 vad_filter: bool = True,
                 vad_parameters: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt or (
            "Реклама, скины, баттлпас Caser, кейсер, Upgrader, апгрейд, DotaGrade, dotagrade, яйцо, рарки на подарки."
        )
        self.vad_filter = vad_filter
        self.vad_parameters = vad_parameters or {
            "min_speech_duration_ms": 250,
            "speech_pad_ms": 400,
            "threshold": 0.32  # Gentle threshold: do not discard quiet speech
        }
        self.model: Optional[WhisperModel] = None
        self._lock = threading.Lock()
        self._init_model()

    def _init_model(self) -> None:
        """Initializes WhisperModel with CUDA or safe fallback."""
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed.")

        # Attempt 1: Requested device & compute_type (e.g. cuda float16)
        try:
            logger.info("Loading WhisperModel(%s, device=%s, compute_type=%s)...",
                        self.model_name, self.device, self.compute_type)
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info("WhisperModel loaded successfully on %s (%s).", self.device, self.compute_type)
            return
        except Exception as e:
            logger.warning("Failed to initialize on %s (%s): %s", self.device, self.compute_type, e)

        # Attempt 2: If cuda float16 failed, try cuda int8_float16 or int8
        if self.device == "cuda":
            for fallback_compute in ["int8_float16", "int8"]:
                try:
                    logger.info("Retrying on CUDA with compute_type=%s...", fallback_compute)
                    self.model = WhisperModel(
                        self.model_name,
                        device="cuda",
                        compute_type=fallback_compute
                    )
                    self.compute_type = fallback_compute
                    logger.info("WhisperModel loaded successfully on CUDA with %s.", fallback_compute)
                    return
                except Exception as e2:
                    logger.warning("CUDA compute_type %s failed: %s", fallback_compute, e2)

        # Attempt 3: CPU fallback (with int8)
        logger.warning("Falling back to CPU device for WhisperModel.")
        try:
            self.device = "cpu"
            self.compute_type = "int8"
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            logger.info("WhisperModel loaded on CPU (int8).")
        except Exception as e3:
            logger.error("Failed to load WhisperModel even on CPU: %s", e3)
            raise e3

    def transcribe(self, audio_path: str, language: Optional[str] = "ru") -> Dict[str, Any]:
        """Transcribes an audio file into text with word timestamps and segment details.
        
        Returns:
            {
                "full_text": str,
                "segments": List[Dict],
                "language": str,
                "language_probability": float
            }
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        if not self.model:
            self._init_model()

        logger.info("Starting transcription of %s...", audio_path)

        with self._lock:
            segments_iter, info = self.model.transcribe(
                audio_path,
                language=language,
                task="transcribe",
                initial_prompt=self.initial_prompt,
                vad_filter=self.vad_filter,
                vad_parameters=self.vad_parameters,
                word_timestamps=True,
                beam_size=5,
                temperature=[0.0, 0.2, 0.4]
            )
            segments_raw = list(segments_iter)

        segments_list: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []

        for seg in segments_raw:
            text = seg.text.strip()
            if text:
                full_text_parts.append(text)

            words_data = []
            if seg.words:
                for w in seg.words:
                    words_data.append({
                        "word": w.word,
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "probability": round(w.probability, 3)
                    })

            segments_list.append({
                "id": seg.id,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": text,
                "words": words_data
            })

        full_text = " ".join(full_text_parts).strip()

        return {
            "full_text": full_text,
            "segments": segments_list,
            "language": info.language,
            "language_probability": round(info.language_probability, 3)
        }
