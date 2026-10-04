@echo off
cd /d "%~dp0"
if exist "%~dp0..\SVG_to_G-code\pythoncore-3.14-64\python.exe" (
  "%~dp0..\SVG_to_G-code\pythoncore-3.14-64\python.exe" "%~dp0PrevodnikNC.py"
) else (
  py -3 "%~dp0PrevodnikNC.py"
)
if errorlevel 1 pause
