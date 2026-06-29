@echo off
setlocal enabledelayedexpansion
echo ============================================
echo  Strollon Development Kit for Windows
echo ============================================
echo.

cd /d "%~dp0\.."

:: ── 1. uv の確認 / インストール ─────────────────────────────
where uv >nul 2>&1
if errorlevel 1 (
    echo [INFO] uv not found. Installing...
    powershell -ExecutionPolicy Bypass -Command ^
        "iwr https://astral.sh/uv/install.ps1 -UseBasicParsing | iex"
    if errorlevel 1 (
        echo [CRITICAL] Failed to install uv.
        echo            Please install manually: https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    :: インストール直後はPATHが通っていないことがあるためリフレッシュ
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
) else (
    for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo [INFO] %%v found.
)

:: ── 2. pyproject.toml の確認 ────────────────────────────────
if not exist pyproject.toml (
    echo [CRITICAL] pyproject.toml not found.
    echo            Please run this script from the project root.
    pause
    exit /b 1
)

:: ── 3. uv sync で依存関係をインストール ─────────────────────
echo.
echo [INFO] Syncing dependencies with uv sync...
uv sync --no-install-project
if errorlevel 1 (
    echo [ERROR] uv sync failed.
    pause
    exit /b 1
)

:: ── 4. pdf.js の配置 ─────────────────────────────────
set "PDFJS_VERSION=5.4.624"
set "PDFJS_URL=https://github.com/mozilla/pdf.js/releases/download/v%PDFJS_VERSION%/pdfjs-%PDFJS_VERSION%-dist.zip"
set "PDFJS_ZIP=%TEMP%\pdfjs-%PDFJS_VERSION%-dist.zip"
set "PDFJS_DEST=resources\pdfjs"

if exist "%PDFJS_DEST%\web\viewer.html" (
    echo [INFO] pdf.js v%PDFJS_VERSION% already present. Skipping.
) else (
    echo [INFO] Downloading pdf.js v%PDFJS_VERSION%...
    powershell -ExecutionPolicy Bypass -Command ^
        "Invoke-WebRequest -Uri '%PDFJS_URL%' -OutFile '%PDFJS_ZIP%' -UseBasicParsing"
    if errorlevel 1 (
        echo [CRITICAL] Failed to download pdf.js.
        echo            URL: %PDFJS_URL%
        pause
        exit /b 1
    )

    echo [INFO] Extracting pdf.js...
    if not exist "%PDFJS_DEST%" mkdir "%PDFJS_DEST%"
    powershell -ExecutionPolicy Bypass -Command ^
        "Expand-Archive -Path '%PDFJS_ZIP%' -DestinationPath '%PDFJS_DEST%' -Force"
    if errorlevel 1 (
        echo [CRITICAL] Failed to extract pdf.js.
        del /f /q "%PDFJS_ZIP%" 2>nul
        pause
        exit /b 1
    )

    del /f /q "%PDFJS_ZIP%" 2>nul
    echo [INFO] pdf.js v%PDFJS_VERSION% installed to %PDFJS_DEST%\
)
echo.

:: ── 5. 完了メッセージ ────────────────────────────────────────
echo.
echo ============================================
echo  [SUCCESS] Environment is ready.
echo ============================================
echo.
echo  Run:
echo    uv run python Strollon.py
echo.
echo  Build:
echo    call scripts\build.bat
echo.
cmd /k
