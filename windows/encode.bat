@echo off
REM Drag a .csv file onto this script to encode it back into a .shn.
REM Its matching .schema.json must sit next to the .csv.
REM Or run:  encode.bat path\to\File.csv
setlocal
if "%~1"=="" (
    echo Usage: drag a .csv file onto this script, or run: encode.bat File.csv
    pause
    exit /b 1
)
python "%~dp0..\fiesta_shn.py" encode %*
echo.
pause
