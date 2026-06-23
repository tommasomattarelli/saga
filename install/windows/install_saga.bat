@echo off
REM ============================================================================
REM SAGA - Windows casual installer (bootstrapper)
REM Download this file and double-click it. It installs Git if needed, clones
REM SAGA, then hands off to install_saga.ps1 for the rest (no Docker required).
REM ============================================================================
setlocal

set "INSTALL_ROOT=%LOCALAPPDATA%\SAGA"
set "APP_DIR=%INSTALL_ROOT%\app"
set "REPO=https://github.com/tommasomattarelli/saga.git"

REM Release the installer checks out. Bumped per release (like the bundle URL).
REM Override with: set SAGA_REF=<tag-or-branch> before running.
set "REF=v0.1.0-beta.1"
if not "%SAGA_REF%"=="" set "REF=%SAGA_REF%"

echo.
echo ========================================
echo   SAGA Installation
echo ========================================
echo.

echo Checking for Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo Git not found. Installing via winget...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    echo.
    echo Git installed. Please CLOSE this window and run install_saga.bat again.
    pause
    exit /b 0
)

if exist "%APP_DIR%\.git" (
    echo Updating existing SAGA install to %REF% ...
    git -C "%APP_DIR%" fetch --tags origin
    git -C "%APP_DIR%" checkout "%REF%"
) else (
    echo Cloning SAGA %REF% into %APP_DIR% ...
    git clone --branch "%REF%" "%REPO%" "%APP_DIR%"
    if errorlevel 1 (
        echo ERROR: clone failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

echo.
echo Running the provisioning step...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\install\windows\install_saga.ps1"

pause
