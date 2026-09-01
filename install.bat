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
    echo Download: https://python.org/downloads
    echo Check "Add to PATH" during install!
    pause
    exit /b 1
)
echo [OK] Python found
echo.
echo [2/3] Install packages...
pip install Flask Flask-SQLAlchemy Flask-Login Flask-WTF Flask-Migrate jdatetime requests reportlab
echo.
echo [3/3] Setup (download fonts + create database)...
python setup.py
echo.
echo ============================================
echo   Install complete! Run: start.bat
echo ============================================
pause
