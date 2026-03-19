@echo off
REM ════════════════════════════════════════════════════════════════
REM  AutoJobAgent — Python Bootstrap + Server Launcher
REM  No admin rights required. Downloads Python 3.11 embed package,
REM  bootstraps pip, installs dependencies, and starts the app.
REM ════════════════════════════════════════════════════════════════
title AutoJobAgent — Starting Server

SET ROOT=%~dp0
SET PY_DIR=%ROOT%python-embed
SET PY=%PY_DIR%\python.exe
SET BACKEND=%ROOT%backend

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  AutoJobAgent — Starting Server          ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── 1. Check if embedded Python already exists ──────────────────
IF EXIST "%PY%" GOTO :INSTALL_DEPS

echo [1/4] Downloading Python 3.11 (portable, no install needed)...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%ROOT%py_embed.zip' -UseBasicParsing"

IF NOT EXIST "%ROOT%py_embed.zip" (
    echo [ERROR] Download failed. Check your internet connection.
    pause & EXIT /B 1
)

echo [2/4] Extracting Python...
powershell -NoProfile -Command "Expand-Archive -Path '%ROOT%py_embed.zip' -DestinationPath '%PY_DIR%' -Force"
del "%ROOT%py_embed.zip" 2>nul

REM ── 2. Enable pip in embed Python ───────────────────────────────
echo [2/4] Enabling pip in embedded Python...

REM Uncomment the 'import site' line in python311._pth
powershell -NoProfile -Command ^
  "(Get-Content '%PY_DIR%\python311._pth') -replace '#import site','import site' | Set-Content '%PY_DIR%\python311._pth'"

REM Download get-pip.py
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PY_DIR%\get-pip.py' -UseBasicParsing"

"%PY%" "%PY_DIR%\get-pip.py" --quiet
IF ERRORLEVEL 1 (
    echo [ERROR] pip bootstrap failed.
    pause & EXIT /B 1
)

:INSTALL_DEPS
REM ── 3. Install dependencies ──────────────────────────────────────
echo [3/4] Installing dependencies (first run may take ~2 min)...
"%PY%" -m pip install flask flask-sqlalchemy flask-migrate flask-login flask-cors ^
  werkzeug python-dotenv requests beautifulsoup4 PyPDF2 python-docx ^
  scikit-learn numpy flashtext markdown aiohttp celery redis playwright firebase-admin ^
  flask-socketio --quiet --disable-pip-version-check

IF ERRORLEVEL 1 (
    echo [ERROR] Dependency install failed.
    pause & EXIT /B 1
)

echo [3.5/4] Installing Playwright browsers...
"%PY%" -m playwright install --with-deps


REM ── 4. Start Flask server ────────────────────────────────────────
echo [4/4] Starting AutoJobAgent server...
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  Open in browser:                        ║
echo  ║  http://127.0.0.1:5000/auth/login        ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  Press Ctrl+C to stop the server.
echo.

cd /d "%BACKEND%"
"%PY%" run.py

pause
