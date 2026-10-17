@echo off
REM SensIntent LLM experiments on the Groq free tier.
REM 1) Put your key in E:\SensIntent\.env as one line:   GROQ_API_KEY=your_key_here
REM 2) Double-click this file.
REM If the daily limit is reached, run it again tomorrow: finished requests are skipped.
cd /d %~dp0code
set HCBXL_PATH=%~dp0..\HCB-XL\hcbxl.py

REM ---- find Python ----
set PY=
where python >nul 2>nul && set PY=python
if not defined PY ( where py >nul 2>nul && set PY=py -3 )
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
)
if not defined PY (
  for /d %%D in ("C:\Program Files\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
)
if not defined PY (
  echo.
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo During installation tick "Add python.exe to PATH", then run this file again.
  goto end
)
echo Using Python: %PY%
%PY% --version
REM no extra libraries needed for the experiments (plain Python 3)

echo.
echo Models available to your Groq account:
%PY% pick_models.py list
for /f "delims=" %%i in ('%PY% pick_models.py large') do set LARGE=%%i
for /f "delims=" %%i in ('%PY% pick_models.py small') do set SMALL=%%i
echo Large model: %LARGE%
echo Small model: %SMALL%
if "%LARGE%"=="" goto end

REM Each model runs in its own window (separate free-tier quotas), results in results\natural_v2
start "SensIntent %LARGE%" cmd /k call "%~dp0RUN_MODEL.bat" %LARGE%
start "SensIntent %SMALL%" cmd /k call "%~dp0RUN_MODEL.bat" %SMALL%
echo.
echo Two windows were opened, one per model. Leave them running.
echo If a window says "daily free-tier limit reached", run RUN_GROQ.bat again tomorrow.
echo When both finish, double-click SCORE.bat to see the comparison table.

:end
pause
