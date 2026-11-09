@echo off
setlocal EnableExtensions
title Upgrade Anime Agent Desktop Pet (face UI fix)

net session >nul 2>&1
if %errorlevel%==0 goto :isadmin
echo.
echo [Administrator required]
echo RIGHT-CLICK this file and choose "Run as administrator".
echo.
pause
exit /b 1

:isadmin
set "SCRIPT_DIR=%~dp0"
set "INSTALLER=%SCRIPT_DIR%..\src-tauri\.tauri-target-user\release\bundle\nsis\Anime Agent Desktop Pet_0.4.0_x64-setup.exe"

echo Stopping app processes...
taskkill /F /IM desktop-pet-gateway.exe >nul 2>&1
taskkill /F /IM canvas-desktop-pet.exe >nul 2>&1
timeout /t 2 /nobreak >nul

if not exist "%INSTALLER%" (
  echo [ERROR] Installer not found: %INSTALLER%
  pause
  exit /b 1
)

echo Running NSIS upgrade (silent)...
"%INSTALLER%" /S /D=C:\Program Files\Anime Agent Desktop Pet
set "RC=%errorlevel%"
echo.
echo Installer exit code: %RC%
timeout /t 3 /nobreak >nul
dir "C:\Program Files\Anime Agent Desktop Pet\gateway\models"
echo.
echo Done. Press any key to close.
pause
exit /b %RC%
