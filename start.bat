@echo off
setlocal
set ROOT_DIR=%~dp0
set BACKEND_PORT=8010
set FRONTEND_PORT=3010

echo ================================================================
echo   Jahtaria Travel Services - U.S. Visa Intelligence Suite
echo   Windows Desktop Launcher (No Docker Required)
echo ================================================================

if not exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  python -m venv "%ROOT_DIR%backend\.venv"
  "%ROOT_DIR%backend\.venv\Scripts\pip.exe" install -r "%ROOT_DIR%backend\requirements.txt"
)

if not exist "%ROOT_DIR%frontend\node_modules" (
  echo [2/3] Installing Next.js frontend packages...
  pushd "%ROOT_DIR%frontend"
  call npm install
  popd
)

echo [3/3] Starting Backend (:%BACKEND_PORT%) and Frontend (:%FRONTEND_PORT%)...
start "Jahtaria Backend" /D "%ROOT_DIR%backend" "%ROOT_DIR%backend\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port %BACKEND_PORT%

timeout /t 3 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%/login"

pushd "%ROOT_DIR%frontend"
if exist ".next" (
  call npx next start -p %FRONTEND_PORT%
) else (
  call npm run dev -- -p %FRONTEND_PORT%
)
popd
