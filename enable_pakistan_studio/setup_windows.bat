@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% neq 0 (
 echo Python launcher not found. Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ and tick Add to PATH.
 pause
 exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 (echo Python setup failed & pause & exit /b 1)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Package installation failed & pause & exit /b 1)
if not exist projects mkdir projects
 echo Setup complete. Double click start_studio.bat
pause
