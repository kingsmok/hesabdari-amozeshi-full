@echo off
chcp 65001 >nul 2>&1
title Academy Manager - Install
echo.
echo ============================================
echo   Academy Manager Pro - Install
echo ============================================
echo.
echo [1/3] Check Python...
set PYTHONUTF8=1
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Download Python 3.11 or 3.12: https://python.org/downloads
    echo Check "Add to PATH" during install!
    pause
    exit /b 1
)
python --version
echo [OK] Python found
echo      Recommended: Python 3.11 or 3.12
echo      Python 3.13/3.14 needs SQLAlchemy 2.0.31 or newer.
echo.
echo [2/3] Install packages (pinned versions from requirements.txt)...
python -m pip install --upgrade pip
pip install -r requirements.txt --upgrade
python -m pip install --upgrade "SQLAlchemy>=2.0.31"
pip install PyQt6 PyQt6-WebEngine
python -c "import sys; from importlib.metadata import version; print('Python', sys.version.split()[0]); print('SQLAlchemy', version('sqlalchemy'))" 2>nul
echo.
echo [3/3] Setup (download fonts + create database)...
python setup.py
echo.
echo ============================================
echo   Install complete! Run: start.bat
echo ============================================
pause
