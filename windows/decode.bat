@echo off
REM Drag a .shn file onto this script to decode it into .csv + .schema.json.
REM Or run:  decode.bat path\to\File.shn
setlocal
if "%~1"=="" (
    echo Usage: drag a .shn file onto this script, or run: decode.bat File.shn
    pause
    exit /b 1
)
python "%~dp0..\fiesta_shn.py" decode %*
echo.
pause
