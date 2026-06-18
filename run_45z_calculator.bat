@echo off
setlocal

set "DOCS=C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs"
set "HTML=lcfs_45z_calculator_v2.html"
set "BUILDER=C:\Users\ehakm\Documents\ELHApp-backend\Calculator_Builder.py"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ACTIVATE="

if exist "C:\Users\ehakm\anaconda3\Scripts\activate.bat" set "ACTIVATE=C:\Users\ehakm\anaconda3\Scripts\activate.bat"
if not defined ACTIVATE if exist "C:\Users\ehakm\miniconda3\Scripts\activate.bat" set "ACTIVATE=C:\Users\ehakm\miniconda3\Scripts\activate.bat"

if not exist "%DOCS%" (
  echo Missing docs folder:
  echo   "%DOCS%"
  pause
  exit /b 1
)

if not defined ACTIVATE (
  echo Could not find an Anaconda or Miniconda activate.bat.
  pause
  exit /b 1
)

if not exist "%BUILDER%" (
  echo Missing calculator builder:
  echo   "%BUILDER%"
  pause
  exit /b 1
)

call "%ACTIVATE%" ethanolq
if errorlevel 1 (
  echo Failed to activate ethanolq.
  pause
  exit /b 1
)

python "%BUILDER%"
if errorlevel 1 (
  echo Failed to build the 45Z calculator HTML.
  pause
  exit /b 1
)

start "45Z Local Server" cmd /k "call ""%ACTIVATE%"" ethanolq && cd /d ""%DOCS%"" && python -m http.server 8011 --bind 127.0.0.1"
timeout /t 3 /nobreak >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8011/' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Local server did not respond at http://127.0.0.1:8011/
  echo Check the "45Z Local Server" window for errors, then try again.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8011/%HTML%"

pause
exit /b 0
