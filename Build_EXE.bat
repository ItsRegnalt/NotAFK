@echo off
title Automate EXE Derleyici (PyInstaller)
cd /d "%~dp0"

echo ==========================================================
echo   AUTOMATE - Standalone EXE Paketi Olusturuluyor...
echo ==========================================================
echo.

cd v2
call npm run build
if errorlevel 1 (
    echo [HATA] UI derlenemedi.
    pause
    exit /b 1
)
cd ..

:: Automate.spec bundles v2/dist, assets, pynput and the WebView2 shell (pywebview + pythonnet)
pyinstaller -y --clean Automate.spec

if errorlevel 1 (
    echo.
    echo [HATA] Derleme sirasinda bir hata olustu.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   DERLEME BASARIYLA TAMAMLANDI!
echo   EXE Konumu: dist\NotAFK\NotAFK.exe
echo ==========================================================
echo.
pause
