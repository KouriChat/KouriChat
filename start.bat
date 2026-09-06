@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0."

rem ============================================================================
rem Editable download settings
rem Change these URLs when the release version or mirror changes.
rem GATEWAY_URL is intentionally empty because the official Release has no gateway.
rem Put a direct community gateway URL here, then start.bat will download it.
rem ============================================================================
set "RELEASE_API_URL=https://api.github.com/repos/KouriChat/KouriChat/releases/latest"
set "RELEASE_API_MIRROR_1=https://ghproxy.net/https://api.github.com/repos/KouriChat/KouriChat/releases/latest"
set "RELEASE_API_MIRROR_2=https://gh-proxy.com/https://api.github.com/repos/KouriChat/KouriChat/releases/latest"
rem 不设置固定版本兜底：必须解析到真实的最新 Release 才允许继续。
set "KOURI_WHL_NAME="
set "ELIXIR_WHL_NAME="
set "KOURI_WHL_URL="
set "ELIXIR_WHL_URL="
set "GATEWAY_FILE=openclaw-onebotv11.exe"
set "GATEWAY_URL="

rem Optional gateway example:
rem set "GATEWAY_URL=https://example.com/path/openclaw-onebotv11.exe"

set "MIRROR_1=https://gh-proxy.com/"
set "MIRROR_2=https://ghproxy.net/"
set "MIRROR_3=https://github.moeyy.xyz/"
set "MIRROR_4=https://ghfast.top/"

goto :bootstrap_uv

:bootstrap_uv
set "UV_CMD=uv"
where uv >nul 2>nul
if not errorlevel 1 goto :prepare_packages
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.cargo\bin\uv.exe"
if exist "%~dp0uv.exe" set "UV_CMD=%~dp0uv.exe"
"%UV_CMD%" --version >nul 2>nul
if not errorlevel 1 goto :prepare_packages

echo [INFO] uv not found. Installing uv...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.cargo\bin\uv.exe"
"%UV_CMD%" --version >nul 2>nul
if not errorlevel 1 goto :prepare_packages

echo [ERROR] uv installation failed. Check your network or permissions.
goto :fail

:prepare_packages
set "PKG_DIR=%~dp0packages"
if not exist "%PKG_DIR%" mkdir "%PKG_DIR%"
rem 先解析真实最新 Release，再决定复用哪个版本的本地缓存。
call :resolve_latest_release
if errorlevel 1 goto :release_failed
set "KOURI_WHL=%PKG_DIR%\%KOURI_WHL_NAME%"
set "ELIXIR_WHL=%PKG_DIR%\%ELIXIR_WHL_NAME%"

if not exist "%KOURI_WHL%" (
    echo [INFO] Downloading latest KouriChat package...
    call :download_wheel "%KOURI_WHL_NAME%" "%KOURI_WHL_URL%" "%KOURI_WHL%"
    if errorlevel 1 goto :download_failed
)
if not exist "%ELIXIR_WHL%" (
    echo [INFO] Downloading latest Elixir core package...
    call :download_wheel "%ELIXIR_WHL_NAME%" "%ELIXIR_WHL_URL%" "%ELIXIR_WHL%"
    if errorlevel 1 goto :download_failed
)

:install_package
where kourichat >nul 2>nul
if not errorlevel 1 goto :start_gateway

echo [INFO] Installing KouriChat and Elixir with uv...
"%UV_CMD%" tool install "%KOURI_WHL%" --with "%ELIXIR_WHL%" --force
if errorlevel 1 goto :install_failed

echo [INFO] Installation completed.

:start_gateway
if not exist "%GATEWAY_FILE%" if defined GATEWAY_URL call :download_gateway
if not exist "%GATEWAY_FILE%" goto :gateway_missing
tasklist /fi "imagename eq %GATEWAY_FILE%" 2>nul | find /i "%GATEWAY_FILE%" >nul
if not errorlevel 1 goto :start_kourichat
echo [INFO] Starting OpenClaw OneBot gateway...
start "OpenClaw OneBot Gateway" "%GATEWAY_FILE%" run
ping 127.0.0.1 -n 3 >nul
goto :start_kourichat

:gateway_missing
echo.
echo [ERROR] Required gateway file is missing: %GATEWAY_FILE%
echo [INFO] Please put %GATEWAY_FILE% beside start.bat.
echo [INFO] Or set GATEWAY_URL at the top of start.bat and run again.
echo [INFO] KouriChat will not start until all required files are ready.
goto :fail

:start_kourichat
where kourichat >nul 2>nul
if errorlevel 1 goto :command_missing
echo [INFO] Starting KouriChat...
kourichat run
goto :finish

:command_missing
echo [ERROR] kourichat command is unavailable after installation.
echo Try opening a new terminal, then run: kourichat run
goto :fail

:release_failed
echo [ERROR] Could not resolve the latest KouriChat Release.
echo Startup is stopped because a fixed or stale version is not allowed.
echo Check API access, mirror settings, or network connectivity.
goto :fail

:download_failed
echo [ERROR] Required wheel download failed.
echo Please check your network, mirror settings, or package URLs at the top of start.bat.
echo KouriChat will not start until both wheel files are ready.
goto :fail

:install_failed
echo [ERROR] uv failed to install KouriChat.
echo Package files are cached in: %PKG_DIR%
echo KouriChat will not start until installation succeeds.
goto :fail

:finish
if not errorlevel 1 goto :success
echo [ERROR] KouriChat exited with code %errorlevel%.
goto :fail

:success
echo [INFO] KouriChat stopped normally.
goto :pause

:fail
echo [INFO] Startup did not complete. Required files are still missing or invalid.
echo Please complete the files above, then run start.bat again.
echo.
echo This window will close automatically in 5 seconds.
for /l %%S in (5,-1,1) do (
    <nul set /p "=Closing in %%S seconds...   "
    powershell -NoProfile -Command "Start-Sleep -Seconds 1"
    echo.
)
exit /b 1

:find_cached_packages
set "CACHED_KOURI_WHL="
set "CACHED_ELIXIR_WHL="
for /f "delims=" %%F in ('dir /b /a-d "%PKG_DIR%\kourichat-*.whl" 2^>nul') do if not defined CACHED_KOURI_WHL set "CACHED_KOURI_WHL=%PKG_DIR%\%%F"
for /f "delims=" %%F in ('dir /b /a-d "%PKG_DIR%\elixir-*.whl" 2^>nul') do if not defined CACHED_ELIXIR_WHL set "CACHED_ELIXIR_WHL=%PKG_DIR%\%%F"
if not defined CACHED_KOURI_WHL exit /b 1
if not defined CACHED_ELIXIR_WHL exit /b 1
exit /b 0

:resolve_latest_release
set "RELEASE_INFO=%TEMP%\kourichat-latest-%RANDOM%.txt"
del /q "%RELEASE_INFO%" >nul 2>nul
for %%A in ("%RELEASE_API_URL%" "%RELEASE_API_MIRROR_1%" "%RELEASE_API_MIRROR_2%") do (
    if not exist "%RELEASE_INFO%" (
        echo [INFO] Resolving latest Release through %%~A
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { $r=Invoke-RestMethod -UseBasicParsing -TimeoutSec 30 -Headers @{ 'User-Agent'='KouriChat-start' } -Uri '%%~A'; $k=$r.assets | Where-Object { $_.name -like 'kourichat-*.whl' } | Select-Object -First 1; $e=$r.assets | Where-Object { $_.name -like 'elixir-*.whl' } | Select-Object -First 1; if ($k -and $e) { ('KOURI_WHL_NAME=' + $k.name),('KOURI_WHL_URL=' + $k.browser_download_url),('ELIXIR_WHL_NAME=' + $e.name),('ELIXIR_WHL_URL=' + $e.browser_download_url) | Out-File -Encoding ascii '%RELEASE_INFO%'; exit 0 }; exit 1 } catch { exit 1 }"
    )
)
if not exist "%RELEASE_INFO%" exit /b 1
for /f "usebackq tokens=1,* delims==" %%A in ("%RELEASE_INFO%") do set "%%A=%%B"
del /q "%RELEASE_INFO%" >nul 2>nul
if not defined KOURI_WHL_NAME exit /b 1
if not defined ELIXIR_WHL_NAME exit /b 1
if not defined KOURI_WHL_URL exit /b 1
if not defined ELIXIR_WHL_URL exit /b 1
echo [INFO] Latest KouriChat package: %KOURI_WHL_NAME%
echo [INFO] Latest Elixir package: %ELIXIR_WHL_NAME%
exit /b 0

:download_gateway
if not defined GATEWAY_URL exit /b 1
echo [INFO] Downloading gateway...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri '%GATEWAY_URL%' -OutFile '%GATEWAY_FILE%.download'; exit 0 } catch { exit 1 }"
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%GATEWAY_FILE%.download'; if ((Test-Path $p) -and ((Get-Item $p).Length -gt 100000) -and ([IO.File]::ReadAllBytes($p)[0] -eq 0x4D) -and ([IO.File]::ReadAllBytes($p)[1] -eq 0x5A)) { exit 0 }; exit 1"
if errorlevel 1 (
    del /q "%GATEWAY_FILE%.download" >nul 2>nul
    exit /b 1
)
move /y "%GATEWAY_FILE%.download" "%GATEWAY_FILE%" >nul
exit /b 0

:download_wheel
set "WHEEL_NAME=%~1"
set "DIRECT_URL=%~2"
set "WHEEL_PATH=%~3"
set "DOWNLOAD_OK=0"

for %%U in (
    "!DIRECT_URL!"
    "!MIRROR_1!!DIRECT_URL!"
    "!MIRROR_2!!DIRECT_URL!"
    "!MIRROR_3!!DIRECT_URL!"
    "!MIRROR_4!!DIRECT_URL!"
) do (
    if "!DOWNLOAD_OK!"=="0" (
        echo [INFO] Trying download source: %%~U
        del /q "!WHEEL_PATH!.download" >nul 2>nul
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 45 -Uri '%%~U' -OutFile '!WHEEL_PATH!.download'; exit 0 } catch { exit 1 }"
        if not errorlevel 1 (
            powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='!WHEEL_PATH!.download'; if ((Test-Path $p) -and ((Get-Item $p).Length -gt 1000)) { $b=[IO.File]::ReadAllBytes($p); if ($b[0] -eq 0x50 -and $b[1] -eq 0x4B) { exit 0 } }; exit 1"
            if not errorlevel 1 (
                move /y "!WHEEL_PATH!.download" "!WHEEL_PATH!" >nul
                set "DOWNLOAD_OK=1"
                echo [INFO] Download succeeded.
            ) else (
                del /q "!WHEEL_PATH!.download" >nul 2>nul
                echo [WARN] Downloaded content was not a valid wheel. Trying next source...
            )
        ) else (
            del /q "!WHEEL_PATH!.download" >nul 2>nul
            echo [WARN] Download source failed. Trying next source...
        )
    )
)

if "!DOWNLOAD_OK!"=="1" exit /b 0
exit /b 1

:pause
pause
exit /b 0
