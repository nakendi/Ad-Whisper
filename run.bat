@echo off
chcp 65001 >nul
title AdWhisper (by @saha12cheh)

echo ========================================================
echo    AdWhisper (by @saha12cheh)
echo    AI TikTok Audio Ad Detector - @twitch.clown
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
    goto :run_app
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_EXE=python"
    goto :run_app
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_EXE=py"
    goto :run_app
)

echo [ОШИБКА] Python 3 не обнаружен в системе!
echo Пожалуйста, установите Python 3 с официального сайта: https://www.python.org/
echo При установке обязательно отметьте галочку: Add Python to PATH.
echo.
pause
exit /b 1

:run_app
echo [ИНФО] Запуск AdWhisper...
echo.
"%PY_EXE%" launcher.py
if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой.
    pause
)
