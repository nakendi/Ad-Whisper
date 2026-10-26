"""Configuration management and target phrase definitions for AdWhisper."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
import yaml

BASE_DIR = Path(__file__).resolve().parent

def ensure_ffmpeg_in_path() -> None:
    """Ensures ffmpeg and ffprobe are accessible in PATH on Windows."""
    # Check if ffmpeg is already available
    import shutil
    if shutil.which("ffmpeg"):
        return

    # Check common winget / local locations
    candidates = [
        BASE_DIR / "runtime" / "bin",
        BASE_DIR / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path("C:/Program Files/ffmpeg/bin"),
        Path("C:/ffmpeg/bin")
    ]
    for c in candidates:
        if c.exists():
            for ffmpeg_exe in c.glob("**/ffmpeg.exe"):
                bin_dir = str(ffmpeg_exe.parent)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return

ensure_ffmpeg_in_path()

@dataclass
class TargetPhrase:
    id: str
    variant_num: int
    name: str
    original_phrase: str
    key_action: str
    target_object_keywords: List[str]
    target_platform_keywords: List[str]
    regex_patterns: List[str]
    description: str

TARGET_VARIANTS: Dict[str, TargetPhrase] = {
    "variant_1": TargetPhrase(
        id="variant_1",
        variant_num=1,
        name="Вариант №1: Яйцо в баттлпассе Caser",
        original_phrase="А улучшить своё яйцо ты можешь в баттлпассе Caser",
        key_action="улучшить",
        target_object_keywords=["яйцо", "своё яйцо", "свое яйцо"],
        target_platform_keywords=[
            "баттлпассе caser", "батлпассе caser", "баттлпасе caser", "батлпасе caser",
            "battle pass caser", "battlepass caser", "caser", "caser.com",
            "баттлпассе кейсера", "батлпассе кейсера", "баттлпасе кейсера", "батлпасе кейсера",
            "battle pass кейсера", "battlepass кейсера", "кейс баттлпас", "кейсера", "кейсер"
        ],
        regex_patterns=[
            r"улучшить\s+(?:сво[её]\s+)?яйц[оауе]\s+(?:ты\s+)?можешь\s+в\s+ба[т]{1,2}лпа[с]{1,2}е\s+(?:caser|кейсер)[ауе]?",
            r"улучш\w+\s+.*?яйц\w+.*?(?:caser|кейсер)\w*",
            r"яйц\w+.*?(?:ба[т]{1,2}лпас|battle\s*pass).*?(?:caser|кейсер)\w*"
        ],
        description="Реклама баттлпасса Caser с яйцом"
    ),
    "variant_2": TargetPhrase(
        id="variant_2",
        variant_num=2,
        name="Вариант №2: Скины на Upgrader",
        original_phrase="А улучшить свои скины ты можешь на Upgrader",
        key_action="улучшить",
        target_object_keywords=["скины", "свои скины", "скин"],
        target_platform_keywords=[
            "на upgrader", "в upgrader", "upgrader", "upgrade", "апгрейдер",
            "на апгрейде", "в апгрейде", "апгрейд", "апгрейде"
        ],
        regex_patterns=[
            r"улучшить\s+(?:свои\s+)?скины\s+(?:ты\s+)?можешь\s+на\s+(?:upgrader|апгрейд\w*)",
            r"улучш\w+\s+.*?скин\w+.*?(?:на\s+)?(?:upgrader|апгрейд)\w*",
            r"скин\w+.*?можешь\s+улучш\w+.*?(?:на\s+)?(?:upgrader|апгрейд)\w*"
        ],
        description="Реклама улучшения скинов на Upgrader"
    ),
    "variant_3": TargetPhrase(
        id="variant_3",
        variant_num=3,
        name="Вариант №3: Рарки на подарки на DotaGrade",
        original_phrase="А улучшить рарки на подарки ты можешь на DotaGrade",
        key_action="улучшить",
        target_object_keywords=["рарки на подарки", "рарки", "подарки", "рар"],
        target_platform_keywords=[
            "dotagrade", "dota dotagrade", "dota grade", "dota upgrade", "dotaupgrade",
            "дота дотагрейд", "дотагрейд", "дота грейд", "дота апгрейд"
        ],
        regex_patterns=[
            r"улучшить\s+рарки\s+на\s+подарки\s+(?:ты\s+)?можешь\s+на\s+(?:dota\s+)?(?:dota|up)?grade\w*",
            r"улучш\w+\s+рарк\w+.*?подарк\w+.*?(?:dota|дота).*?(?:grade|грейд)\w*",
            r"рарк\w+\s+на\s+подарк\w+.*?(?:dotagrade|дотагрейд|dota\s*grade)\w*"
        ],
        description="Реклама DotaGrade (рарки на подарки)"
    )
}

def load_config(config_path: Path = None) -> Dict[str, Any]:
    """Loads configuration from YAML with defaults."""
    if config_path is None:
        config_path = BASE_DIR / "config.yaml"
    
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Ensure paths are resolved
    storage = data.get("storage", {})
    for key in ["db_path", "temp_audio_dir", "demucs_output_dir", "export_dir"]:
        if key in storage:
            p = BASE_DIR / storage[key]
            storage[key] = str(p)
            p.parent.mkdir(parents=True, exist_ok=True)
            if "dir" in key:
                p.mkdir(parents=True, exist_ok=True)
    
    return data
