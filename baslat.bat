@echo off
setlocal
cd /d "%~dp0"
title 999 Badge

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 main.py
    goto end
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python main.py
    goto end
)

where python3 >nul 2>nul
if %errorlevel% equ 0 (
    python3 main.py
    goto end
)

echo.
echo ========================================================
echo  HATA: Bilgisayarinizda Python bulunamadi!
echo  Lutfen https://www.python.org adresinden Python kurun.
echo  Kurulumda Add python.exe to PATH kutusunu isaretleyin!
echo ========================================================
echo.

:end
if %errorlevel% neq 0 (
    echo.
    echo Program kapandi.
)
pause
