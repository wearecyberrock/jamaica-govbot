@echo off
setlocal EnableDelayedExpansion
set "ROOT_DIR=%~dp0"
set "BACKEND_PORT=8010"
set "FRONTEND_PORT=3010"

echo ================================================================
echo   Jahtaria Travel Services - U.S. Visa Intelligence Suite
echo   Windows Desktop Launcher (No Docker Required)
echo ================================================================
echo.

REM --- Detect a real Python 3 installation (bypassing Windows Store stub) ---
set "PY_CMD="

for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python313\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%ProgramFiles%\Python311\python.exe"
) do (
  if not defined PY_CMD if exist %%~P (
    set "PY_CMD=%%~P"
  )
)

if not defined PY_CMD (
  py -3 --version >nul 2>&1
  if !errorlevel! equ 0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
  python --version 2>&1 | findstr /R /C:"Python 3\." >nul 2>&1
  if !errorlevel! equ 0 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo [!] Python 3 was not found on this PC.
  echo [*] Attempting automatic install of Python 3.12 via Windows winget...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%ProgramFiles%\Python312\python.exe"
  ) do (
    if exist %%~P set "PY_CMD=%%~P"
  )
)

if not defined PY_CMD (
  echo.
  echo [ERROR] Python 3.11+ is required to run the backend.
  echo Please install Python 3.12 from: https://www.python.org/downloads/
  echo IMPORTANT: Check "Add python.exe to PATH" during installation,
  echo then double-click start.bat again.
  echo.
  pause
  exit /b 1
)

echo [OK] Using Python: %PY_CMD%

REM --- 1. Create venv & install backend packages ---
if not exist "%ROOT_DIR%backend\.venv\Scripts\uvicorn.exe" (
  echo [1/3] Setting up Python virtual environment and backend packages...
  if exist "%ROOT_DIR%backend\.venv" rmdir /s /q "%ROOT_DIR%backend\.venv"
  %PY_CMD% -m venv "%ROOT_DIR%backend\.venv"
  if errorlevel 1 (
    echo [ERROR] Failed to create Python virtual environment.
    pause
    exit /b 1
  )
  "%ROOT_DIR%backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
  "%ROOT_DIR%backend\.venv\Scripts\pip.exe" install -r "%ROOT_DIR%backend\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Failed to install backend Python packages.
    pause
    exit /b 1
  )
) else (
  echo [1/3] Backend virtual environment already ready.
)

REM --- 2. Install Next.js frontend packages if needed ---
if not exist "%ROOT_DIR%frontend\node_modules" (
  echo [2/3] Installing Next.js frontend packages...
  pushd "%ROOT_DIR%frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo [ERROR] Failed to install Node.js packages. Make sure Node.js 20+ is installed.
    pause
    exit /b 1
  )
  popd
) else (
  echo [2/3] Frontend node_modules already ready.
)

REM --- 3. Launch Backend & Frontend ---
echo [3/3] Starting Backend (:%BACKEND_PORT%) and Frontend (:%FRONTEND_PORT%)...
start "Jahtaria Backend (:%BACKEND_PORT%)" /D "%ROOT_DIR%backend" "%ROOT_DIR%backend\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port %BACKEND_PORT%

echo Waiting for backend to initialize...
timeout /t 4 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%/login"

pushd "%ROOT_DIR%frontend"
if exist ".next" (
  call npx next start -p %FRONTEND_PORT%
) else (
  call npm run dev -- -p %FRONTEND_PORT%
)
popd
