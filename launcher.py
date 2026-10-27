"""AdWhisper — Desktop Launcher & Optimizer.
Compiles into AdWhisper.exe (without console) and is invoked by run.bat (with console).

Features:
1. Safe execution in both windowless GUI mode and terminal/batch mode.
2. PC Hardware Diagnostics (GPU, VRAM, CPU cores) & auto-optimization of config.yaml.
3. Model Download & Verification (faster-whisper large-v3).
4. Window size adaptation based on user's display resolution.
5. Launches Streamlit application and dedicated desktop app window (Edge/Chrome).
6. Automatic port resolution (frees 8501 or finds next available port).
7. Foolproof lifecycle: keeps server running and prevents ERR_CONNECTION_REFUSED.
"""

import ctypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

# Safe logging for windowless GUI / noconsole mode
class SafeStream:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._f = None

    def write(self, s):
        if not s:
            return
        try:
            if self._f is None:
                self._f = open(self.log_path, "a", encoding="utf-8", errors="replace")
            self._f.write(s)
            self._f.flush()
        except Exception:
            pass

    def flush(self):
        try:
            if self._f:
                self._f.flush()
        except Exception:
            pass

base_dir = get_base_dir()
log_file = base_dir / "launcher.log"

is_gui_mode = sys.stdout is None

if sys.stdout is None:
    sys.stdout = SafeStream(log_file)
else:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = SafeStream(log_file)
else:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def get_py_exec() -> str:
    base_dir = get_base_dir()
    candidates = [
        base_dir / "runtime" / "python.exe",
        base_dir / ".venv" / "Scripts" / "python.exe",
        base_dir.parent / ".venv" / "Scripts" / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    for cmd in ["python", "py"]:
        p = shutil.which(cmd)
        if p and not any(exe in p.lower() for exe in ["adwhisper", "bannerscanner", "tiktokaudioscanner"]):
            return p

    return ""

def setup_dll_paths():
    base_dir = get_base_dir()
    # 1. Prepend local FFmpeg directories to the front of PATH so system / WinGet / AppData are never used
    for bin_cand in [base_dir / "bin", base_dir / "ffmpeg", base_dir / "runtime" / "bin"]:
        if bin_cand.exists():
            os.environ["PATH"] = str(bin_cand) + os.pathsep + os.environ.get("PATH", "")

    # 2. Add NVIDIA CUDA DLLs
    for sp_candidate in [base_dir / "runtime" / "Lib" / "site-packages", base_dir / ".venv" / "Lib" / "site-packages"]:
        if sp_candidate.exists():
            for pkg in ["nvidia/cublas/bin", "nvidia/cudnn/bin"]:
                p = sp_candidate / Path(pkg)
                if p.exists():
                    try:
                        if hasattr(os, "add_dll_directory"):
                            os.add_dll_directory(str(p))
                        os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
                    except Exception:
                        pass

setup_dll_paths()

# Set explicit AppUserModelID for proper Windows taskbar grouping & icon
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("saha12cheh.adwhisper.app.1.0")
    except Exception:
        pass

def check_hardware_info():
    """Detects GPU and CPU for diagnostic logging without overwriting user settings."""
    print("\n[1/2] Проверка оборудования...")

    gpu_name = None
    vram_mb = 0

    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True,
            creationflags=CREATE_NO_WINDOW
        )
        output = res.stdout.strip()
        if output:
            parts = [p.strip() for p in output.split(",")]
            gpu_name = parts[0]
            vram_mb = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    except Exception:
        pass

    if not gpu_name:
        try:
            wmi_res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW
            )
            for line in wmi_res.stdout.splitlines():
                line = line.strip()
                if "NVIDIA" in line.upper():
                    gpu_name = line
                    break
        except Exception:
            pass

    cpu_info = "Неизвестный CPU"
    try:
        cpu_res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_Processor).Name"],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW
        )
        cpu_info = cpu_res.stdout.strip().splitlines()[0] if cpu_res.stdout.strip() else cpu_info
    except Exception:
        pass

    print(f"      • Процессор: {cpu_info}")
    if gpu_name:
        vram_str = f" ({vram_mb} MB VRAM)" if vram_mb > 0 else ""
        print(f"      • Видеокарта: {gpu_name}{vram_str}")
    else:
        print("      • Видеокарта: NVIDIA GPU не обнаружен (режим CPU)")

def ensure_ffmpeg_in_path():
    if shutil.which("ffmpeg"):
        return True
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path("C:/Program Files/ffmpeg/bin"),
        Path("C:/ffmpeg/bin")
    ]
    for c in candidates:
        if c.exists():
            for ffmpeg_exe in c.glob("**/ffmpeg.exe"):
                bin_dir = str(ffmpeg_exe.parent)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return True
    return False

def get_screen_dimensions():
    try:
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        if sw > 0 and sh > 0:
            return sw, sh
    except Exception:
        pass
    return 1920, 1080

def find_standalone_browser():
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def is_server_ready(port: int, timeout=1) -> bool:
    for path in ["/_stcore/health", "/"]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"User-Agent": "HealthCheck"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
    return False

def free_port(port=8501):
    """Frees the specified port if occupied by any lingering background process."""
    if sys.platform != "win32":
        return
    try:
        ps_cmd = (
            f"$p = (Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess; "
            f"if ($p) {{ Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=5
        )
    except Exception:
        pass

def get_available_port(start_port=8501) -> int:
    free_port(start_port)
    time.sleep(0.5)

    for port in [start_port] + list(range(8502, 8520)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port

def launch_application():
    """Starts Streamlit and opens the application window."""
    print("\n[2/2] Запуск интерфейса AdWhisper...")
    sw, sh = get_screen_dimensions()

    win_w = min(1540, max(1100, int(sw * 0.86)))
    win_h = min(940, max(750, int(sh * 0.88)))
    win_x = max(10, (sw - win_w) // 2)
    win_y = max(10, (sh - win_h) // 2)

    base_dir = get_base_dir()
    py_exec = get_py_exec()

    if not py_exec:
        msg = "Python 3 не найден на компьютере.\n\nПожалуйста, установите Python с сайта https://www.python.org/, отметив галочку 'Add Python to PATH'."
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(0, msg, "AdWhisper — Ошибка", 0x10)
        print(f"[ОШИБКА] {msg}")
        return

    # Auto-initialize .venv if missing (e.g. fresh clone from GitHub)
    venv_py = base_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        try:
            print("Создание виртуального окружения .venv...")
            subprocess.run([py_exec, "-m", "venv", str(base_dir / ".venv")], check=True, creationflags=CREATE_NO_WINDOW)
            if venv_py.exists():
                py_exec = str(venv_py)
                print("Установка зависимостей из requirements.txt...")
                subprocess.run([py_exec, "-m", "pip", "install", "--upgrade", "pip"], check=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run([py_exec, "-m", "pip", "install", "-r", str(base_dir / "requirements.txt")], check=True, creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            print(f"Ошибка инициализации окружения: {e}")

    app_port = get_available_port(8501)
    target_url = f"http://127.0.0.1:{app_port}"

    server_proc = None
    if not is_server_ready(app_port):
        cmd = [
            py_exec, "-m", "streamlit", "run", "app.py",
            "--server.address", "127.0.0.1",
            "--server.port", str(app_port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ]
        flags = CREATE_NO_WINDOW if is_gui_mode else 0
        st_log_file = open(base_dir / "streamlit.log", "a", encoding="utf-8")
        
        server_proc = subprocess.Popen(
            cmd,
            cwd=str(base_dir),
            stdin=subprocess.DEVNULL,
            stdout=st_log_file,
            stderr=subprocess.STDOUT,
            creationflags=flags
        )

        ready = False
        for _ in range(75):
            if is_server_ready(app_port):
                ready = True
                break
            if server_proc.poll() is not None:
                print(f"[ОШИБКА] Streamlit завершился с кодом {server_proc.returncode}!")
                break
            time.sleep(0.4)

        if not ready:
            print("Предупреждение: Сервер долго запускается...")
        else:
            print(f"Сервер готов (HTTP 200): {target_url}")

    browser_exe = find_standalone_browser()
    app_proc = None

    if browser_exe:
        profile_dir = Path(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", "."))) / "AdWhisperBrowserProfile"
        app_cmd = [
            browser_exe,
            f"--app={target_url}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={win_w},{win_h}",
            f"--window-position={win_x},{win_y}"
        ]
        flags = CREATE_NO_WINDOW if is_gui_mode else 0
        app_proc = subprocess.Popen(
            app_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )
    else:
        import webbrowser
        webbrowser.open(target_url)

    start_time = time.time()
    try:
        if app_proc:
            app_proc.wait()
            if time.time() - start_time > 5:
                if server_proc:
                    try:
                        server_proc.terminate()
                        server_proc.wait(timeout=2)
                    except Exception:
                        pass
                return
            else:
                if server_proc:
                    server_proc.wait()
                else:
                    while True:
                        time.sleep(2)
        elif server_proc:
            server_proc.wait()
        else:
            while True:
                time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if server_proc:
            try:
                server_proc.terminate()
            except Exception:
                pass

def main():
    try:
        check_hardware_info()
        ensure_ffmpeg_in_path()
        launch_application()
    except Exception as e:
        print(f"Критическая ошибка запуска: {e}")
        if is_gui_mode and sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(0, f"Ошибка запуска AdWhisper:\n\n{e}", "AdWhisper", 0x10)

if __name__ == "__main__":
    main()
