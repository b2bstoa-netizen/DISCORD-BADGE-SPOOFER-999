@echo off
chcp 65001 > nul
title 999 Badge - Discord Profil Rozet Yöneticisi
cd /d "%~dp0"
py -3 main.py
if %errorlevel% neq 0 (
    echo.
    echo Bir hata oluştu veya program kapandı.
    pause
)
