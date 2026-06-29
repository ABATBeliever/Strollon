@echo off
setlocal

cd /d %~dp0\..

echo [INFO] Cleanup...
del /f uv.lock
del /f nuitka-crash-report.xml
rmdir /S /Q .venv
rmdir /S /Q "Strollon.build"
rmdir /S /Q "Strollon.dist"
rmdir /S /Q "Strollon.onefile-build"
rmdir /S /Q "__pycache__"

rmdir /S /Q "data"
rmdir /S /Q "state"
rmdir /S /Q "cache"
rmdir /S /Q "config"
rmdir /S /Q "resources"

endlocal
exit /b