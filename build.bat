@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Build - Hesabdari Rahsa

REM ===========================================================================
REM  Local CI/CD pipeline
REM    1. clean old build artefacts
REM    2. build the onedir executable with PyInstaller (app.spec)
REM    3. compile the Windows installer with Inno Setup (setup.iss)
REM  Any failing step aborts the script with a non-zero exit code so the
REM  batch file can also be used from a scheduler or another CI runner.
REM ===========================================================================

set "APP_NAME=AcademyManager"
set "SPEC_FILE=app.spec"
set "ISS_FILE=setup.iss"
set "DIST_DIR=dist\%APP_NAME%"
set "OUTPUT_DIR=installer_output"

REM Always run from the folder that contains this script
pushd "%~dp0"

echo.
echo ==========================================================
echo   Build pipeline - Hesabdari Rahsa
echo ==========================================================
echo.

REM ---------------------------------------------------------------------------
REM  Step 0/4 - Toolchain check
REM ---------------------------------------------------------------------------
echo [0/4] Checking the toolchain...

python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python was not found in PATH.
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo   - %%v

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] PyInstaller is not installed. Run: pip install pyinstaller
    goto :fail
)
for /f "delims=" %%v in ('python -m PyInstaller --version 2^>^&1') do echo   - PyInstaller %%v

REM Locate the Inno Setup command line compiler (ISCC.exe)
set "ISCC="
where ISCC.exe >nul 2>&1 && set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo   [ERROR] Inno Setup 6 (ISCC.exe) was not found.
    echo           Download it from https://jrsoftware.org/isinfo.php
    goto :fail
)
echo   - Inno Setup: %ISCC%

if not exist "%SPEC_FILE%" (
    echo   [ERROR] %SPEC_FILE% is missing.
    goto :fail
)
if not exist "%ISS_FILE%" (
    echo   [ERROR] %ISS_FILE% is missing.
    goto :fail
)

REM ---------------------------------------------------------------------------
REM  Step 1/4 - Clean previous artefacts
REM ---------------------------------------------------------------------------
echo.
echo [1/4] Cleaning old build output...

if exist "build" (
    rmdir /s /q "build"
    if exist "build" (
        echo   [ERROR] Could not delete .\build - is a file still open?
        goto :fail
    )
    echo   - removed .\build
)

if exist "dist" (
    rmdir /s /q "dist"
    if exist "dist" (
        echo   [ERROR] Could not delete .\dist - is the application still running?
        goto :fail
    )
    echo   - removed .\dist
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
echo   - output folder: %OUTPUT_DIR%

REM ---------------------------------------------------------------------------
REM  Step 2/4 - Build the executable
REM ---------------------------------------------------------------------------
echo.
echo [2/4] Building the executable with PyInstaller...
python -m PyInstaller --noconfirm --clean "%SPEC_FILE%"
if errorlevel 1 (
    echo   [ERROR] PyInstaller failed. See the log above.
    goto :fail
)
if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo   [ERROR] %DIST_DIR%\%APP_NAME%.exe was not produced.
    goto :fail
)
echo   - built: %DIST_DIR%\%APP_NAME%.exe

REM ---------------------------------------------------------------------------
REM  Step 3/4 - Compile the installer
REM ---------------------------------------------------------------------------
echo.
echo [3/4] Compiling the installer with Inno Setup...
"%ISCC%" /Q "%ISS_FILE%"
if errorlevel 1 (
    echo   [ERROR] Inno Setup failed. See the log above.
    goto :fail
)

REM ---------------------------------------------------------------------------
REM  Step 4/4 - Report
REM ---------------------------------------------------------------------------
echo.
echo [4/4] Verifying the result...
REM Pick the most recently written installer (dir /o-d sorts by date, newest first)
set "SETUP_FILE="
for /f "delims=" %%f in ('dir /b /o-d "%OUTPUT_DIR%\*.exe" 2^>nul') do (
    if not defined SETUP_FILE set "SETUP_FILE=%CD%\%OUTPUT_DIR%\%%f"
)
if not defined SETUP_FILE (
    echo   [ERROR] No installer was found in %OUTPUT_DIR%.
    goto :fail
)

echo.
echo ==========================================================
echo   BUILD SUCCEEDED
echo ----------------------------------------------------------
echo   Application : %CD%\%DIST_DIR%\%APP_NAME%.exe
echo   Installer   : %SETUP_FILE%
echo ==========================================================
echo.
popd
endlocal
exit /b 0

:fail
echo.
echo ==========================================================
echo   BUILD FAILED
echo ==========================================================
echo.
popd
endlocal
exit /b 1
