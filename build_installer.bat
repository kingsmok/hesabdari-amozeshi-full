@echo off
setlocal
title Academy Manager Pro - Build Installer

echo.
echo ============================================================
echo    Academy Manager Pro - Build Installer
echo    (this window stays open until you close it)
echo ============================================================
echo.

rem =============================================================
rem  NOTE: this file is intentionally 100 percent ASCII.
rem  cmd.exe has a known bug with batch files that contain
rem  Persian text (code page 65001): the window opens and
rem  closes immediately. All the real work, and all the
rem  Persian messages, are done by build_installer.py which
rem  this file simply calls. Do NOT add non-ASCII text here.
rem =============================================================

pushd "%~dp0"

where python >nul 2>&1
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed correctly, or it is not in PATH.
    echo.
    echo  Fix:
    echo     1. Download Python 3.10 or newer from https://www.python.org/downloads/
    echo     2. During installation, tick the box  Add python.exe to PATH
    echo     3. Close this window and run this file again
    echo.
    pause
    exit /b 1
)

echo [OK] Python found. Starting the build ...
echo      On the first run this can take 10 to 30 minutes.
echo.

python "%~dp0build_installer.py"
set "RC=%errorlevel%"
popd

echo.
if "%RC%"=="0" (
    echo ============================================================
    echo  Build finished. See the messages above for the result.
    echo ============================================================
) else (
    echo ============================================================
    echo  Build stopped with error code %RC%.
    echo  Read the messages above to find the cause.
    echo ============================================================
)

echo.
pause
exit /b %RC%
