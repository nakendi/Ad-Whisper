"""AdWhisper In-App OTA Updater.
Checks GitHub repository for updates and installs updated source scripts seamlessly.
"""

import io
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

REPO_OWNER = "nakendi"
REPO_NAME = "Ad-Whisper"
BRANCH = "main"

# Files that should be updated from GitHub
ALLOWED_UPDATE_EXTENSIONS = {".py", ".bat", ".iss", ".txt", ".ico", ".png", ".md"}
PROTECTED_FILES = {"config.yaml", "scanner.db"}
PROTECTED_DIRS = {"data", ".venv", "runtime", "installer_output", "__pycache__"}


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def get_local_version() -> str:
    """Returns local commit SHA or version string."""
    base_dir = get_base_dir()
    v_file = base_dir / ".version"
    if v_file.exists():
        try:
            val = v_file.read_text(encoding="utf-8").strip()
            if val:
                return val[:7]
        except Exception:
            pass

    # Try git if available in dev environment
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return "2924a8c"


def check_for_updates() -> Dict[str, Any]:
    """Queries GitHub API for the latest commit on main.

    Returns dict with update status and commit metadata.
    """
    local_sha = get_local_version()
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "AdWhisper-Updater",
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                remote_sha = data.get("sha", "")[:7]
                commit_info = data.get("commit", {})
                msg = commit_info.get("message", "").splitlines()[0] if commit_info.get("message") else "Обновление компонентов"
                date_str = commit_info.get("author", {}).get("date", "")[:10]

                has_update = bool(remote_sha and remote_sha.lower() != local_sha.lower())
                return {
                    "has_update": has_update,
                    "local_sha": local_sha,
                    "remote_sha": remote_sha,
                    "message": msg,
                    "date": date_str,
                    "error": None
                }
    except Exception as e:
        logger.warning("Failed to check for updates: %s", e)
        return {
            "has_update": False,
            "local_sha": local_sha,
            "remote_sha": local_sha,
            "message": "",
            "date": "",
            "error": str(e)
        }

    return {
        "has_update": False,
        "local_sha": local_sha,
        "remote_sha": local_sha,
        "message": "",
        "date": "",
        "error": "Неизвестный ответ сервера"
    }


def apply_update(remote_sha: Optional[str] = None) -> Tuple[bool, str]:
    """Downloads main.zip from GitHub and updates application code files.

    Protects user data, database, and config.yaml.
    """
    base_dir = get_base_dir()
    zip_url = f"https://github.com/nakendi/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"
    req = urllib.request.Request(zip_url, headers={"User-Agent": "AdWhisper-Updater"})

    try:
        logger.info("Downloading update archive from %s...", zip_url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            zip_bytes = resp.read()

        updated_count = 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for member in z.infolist():
                if member.is_dir():
                    continue

                # Paths in zip are typically: Ad-Whisper-main/<rel_path>
                parts = Path(member.filename).parts
                if len(parts) <= 1:
                    continue
                rel_parts = parts[1:]
                top_dir = rel_parts[0] if len(rel_parts) > 1 else ""

                if top_dir in PROTECTED_DIRS:
                    continue

                filename = rel_parts[-1]
                if filename in PROTECTED_FILES:
                    continue

                ext = Path(filename).suffix.lower()
                if ext not in ALLOWED_UPDATE_EXTENSIONS:
                    continue

                target_path = base_dir.joinpath(*rel_parts)
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with z.open(member) as src_f, open(target_path, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                updated_count += 1

        # Save new version SHA
        target_sha = remote_sha or "latest"
        (base_dir / ".version").write_text(target_sha, encoding="utf-8")

        return True, f"Успешно обновлено {updated_count} файлов (версия {target_sha})!"

    except Exception as e:
        logger.error("Update installation failed: %s", e)
        return False, f"Ошибка при установке обновления: {e}"
