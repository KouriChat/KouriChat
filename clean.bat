@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0."

echo ========================================
echo KouriChat cleanup
echo ========================================
echo.
echo This will remove:
echo   - The uv tool installation: kourichat
echo   - Downloaded wheel files in packages\
echo   - Local virtual environments: .venv\ and venv\
echo.
echo It will keep:
echo   - kourichat.toml
echo   - data\ and other user files
echo.
choice /c YN /n /d Y /t 5 /m "Continue cleanup? [Y/N] "
if errorlevel 2 goto :cancel

set "UV_CMD=uv"
where uv >nul 2>nul
if errorlevel 1 if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
if errorlevel 1 if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.cargo\bin\uv.exe"

"%UV_CMD%" --version >nul 2>nul
if errorlevel 1 goto :skip_uv

"%UV_CMD%" tool list 2>nul | findstr /i /c:"kourichat" >nul
if errorlevel 1 goto :uninstall_uv_tool

echo [INFO] Uninstalling uv tool: kourichat...
"%UV_CMD%" tool uninstall kourichat
if errorlevel 1 echo [WARN] uv could not uninstall kourichat.

goto :remove_files

:uninstall_uv_tool
echo [INFO] kourichat uv tool is not installed.

:skip_uv
echo [WARN] uv was not found. Skipping uv tool uninstall.

goto :remove_files

:remove_files
if exist "packages" (
    echo [INFO] Removing downloaded wheel cache: packages\
    rmdir /s /q "packages"
    if exist "packages" (echo [WARN] Could not remove packages\.) else (echo [OK] packages\ removed.)
) else (
    echo [INFO] No packages\ directory found.
)

if exist ".venv" (
    echo [INFO] Removing local virtual environment: .venv\
    rmdir /s /q ".venv"
    if exist ".venv" (echo [WARN] Could not remove .venv\.) else (echo [OK] .venv\ removed.)
)

if exist "venv" (
    echo [INFO] Removing local virtual environment: venv\
    rmdir /s /q "venv"
    if exist "venv" (echo [WARN] Could not remove venv\.) else (echo [OK] venv\ removed.)
)

echo.
echo [OK] Dependency cleanup completed.
echo [INFO] kourichat.toml and data\ were kept.
goto :pause

:cancel
echo [INFO] Cleanup cancelled.

goto :pause

:pause
echo.
echo This window will close automatically in 5 seconds.
for /l %%S in (5,-1,1) do (
    <nul set /p "=Closing in %%S seconds...   "
    powershell -NoProfile -Command "Start-Sleep -Seconds 1"
    echo.
)
exit /b 0
