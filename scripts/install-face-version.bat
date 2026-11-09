@echo off
setlocal EnableExtensions
title Install Anime Agent Desktop Pet (Face / SFace)

rem ---- Check administrator rights ----
net session >nul 2>&1
if %errorlevel%==0 goto :isadmin

echo.
echo [Administrator required]
echo Please close this window, then RIGHT-CLICK this file and choose
echo "Run as administrator".
echo.
pause
exit /b 1

:isadmin
set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%_install_face_nsis.ps1"
set "INSTALLER=%SCRIPT_DIR%..\src-tauri\.tauri-target-user\release\bundle\nsis\Anime Agent Desktop Pet_0.4.0_x64-setup.exe"

echo ============================================================
echo  Steps: stop processes -^> uninstall old MSI -^> install new NSIS
echo  PowerShell: %PS1%
echo  Installer : %INSTALLER%
echo ============================================================
echo.

if not exist "%PS1%" (
  echo [ERROR] PowerShell script not found: %PS1%
  pause
  exit /b 1
)
if not exist "%INSTALLER%" (
  echo [ERROR] Installer not found: %INSTALLER%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Installer "%INSTALLER%"
set "RC=%errorlevel%"

echo.
echo ============================================================
echo  Finished, exit code %RC% (0 = success).
echo  Log: %%TEMP%%\deskpet-install.log
echo ============================================================
pause
exit /b %RC%
