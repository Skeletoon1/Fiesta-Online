@echo off
REM Drag a .shn file onto this script to check it round-trips byte-for-byte.
REM Or run:  verify.bat path\to\File.shn
setlocal
if "%~1"=="" (
    echo Usage: drag a .shn file onto this script, or run: verify.bat File.shn
    pause
    exit /b 1
)
python "%~dp0..\fiesta_shn.py" verify %*
echo.
pause
