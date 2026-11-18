@echo off
title Automate
cd /d "%~dp0"

:: Siyah konsol penceresini gizleyerek sessizce (pythonw ile) baslat
start "" pythonw main.py
if errorlevel 1 (
    :: Eger pythonw bulunamazsa normal python ile calistirip hatayi goster
    python main.py
    if errorlevel 1 (
        echo.
        echo Bir hata olustu. Cikmak icin bir tusa basin...
        pause >nul
    )
)
