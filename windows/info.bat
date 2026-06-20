@echo off
REM Drag a .shn file onto this script to print its header and columns.
REM Or run:  info.bat path\to\File.shn
setlocal
if "%~1"=="" (
    echo Usage: drag a .shn file onto this script, or run: info.bat File.shn
    pause
    exit /b 1
)
python "%~dp0..\fiesta_shn.py" info %*
echo.
pause
