@echo off
chcp 65001 >nul
title E-Faktura Tizimi

echo.
echo =================================================
echo    Elektron Hisob-Faktura Tizimi
echo =================================================
echo.

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -File ".\start.ps1"

pause
