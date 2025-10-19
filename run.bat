@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: 璁剧疆鎺у埗鍙扮紪鐮佷负 GBK
chcp 936 >nul
title KouriChat 鍚姩鍣�

cls
echo ====================================
echo         K O U R I   C H A T
echo ====================================
echo.
echo 鈺斺晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晽
echo 鈺�       KouriChat - AI Chat        鈺�
echo 鈺�  Created with Heart by KouriTeam 鈺�
echo 鈺氣晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨暆
echo KouriChat - AI Chat  Copyright (C) 2025, DeepAnima Network Technology Studio
echo.

:: 娣诲姞閿欒鎹曡幏
echo [灏濊瘯] 姝ｅ湪鍚姩绋嬪簭鍠�...

:: 妫�娴� Python 鏄惁宸插畨瑁�
echo [妫�娴媇 姝ｅ湪妫�娴婸ython鐜鍠�...
python --version >nul 2>&1
if errorlevel 1 (
    echo [閿欒] Python鏈畨瑁咃紝璇峰厛瀹夎Python鍠�...   
    echo.
    echo 鎸変换鎰忛敭閫�鍑�...
    pause >nul
    exit /b 1
)

:: 妫�娴� Python 鐗堟湰
for /f "tokens=2" %%I in ('python -V 2^>^&1') do set PYTHON_VERSION=%%I
echo [灏濊瘯] 妫�娴嬪埌Python鐗堟湰: !PYTHON_VERSION!
for /f "tokens=2 delims=." %%I in ("!PYTHON_VERSION!") do set MINOR_VERSION=%%I
if !MINOR_VERSION! GEQ 13 (
    echo [璀﹀憡] 涓嶆敮鎸� Python 3.12 鍙婃洿楂樼増鏈柕...
    echo [璀﹀憡] 璇蜂娇鐢� Python 3.11 鎴栨洿浣庣増鏈柕...
    echo.
    echo 鎸変换鎰忛敭閫�鍑�...
    pause >nul
    exit /b 1
)

:: 璁剧疆铏氭嫙鐜鐩綍
set VENV_DIR=.venv

:: 濡傛灉铏氭嫙鐜涓嶅瓨鍦ㄦ垨婵�娲昏剼鏈笉瀛樺湪锛屽垯閲嶆柊鍒涘缓
if not exist %VENV_DIR% (
    goto :create_venv
) else if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [璀﹀憡] 铏氭嫙鐜浼间箮宸叉崯鍧忥紝姝ｅ湪閲嶆柊鍒涘缓鍠�...
    rmdir /s /q %VENV_DIR% 2>nul
    goto :create_venv
) else (
    goto :activate_venv
)

:create_venv
echo [灏濊瘯] 姝ｅ湪鍒涘缓铏氭嫙鐜鍠�...
python -m venv %VENV_DIR% 2>nul
if errorlevel 1 (
    echo [閿欒] 鍒涘缓铏氭嫙鐜澶辫触鍠�...
    echo.
    echo 鍙兘鍘熷洜:
    echo 1. Python venv 妯″潡鏈畨瑁呭柕...
    echo 2. 鏉冮檺涓嶈冻鍠�...
    echo 3. 纾佺洏绌洪棿涓嶈冻鍠�...
    echo.
    echo 灏濊瘯瀹夎 venv 妯″潡鍠�...
    python -m pip install virtualenv
    if errorlevel 1 (
        echo [閿欒] 瀹夎 virtualenv 澶辫触
        echo.
        echo 鎸変换鎰忛敭閫�鍑�...
        pause >nul
        exit /b 1
    )
    echo [灏濊瘯] 浣跨敤 virtualenv 鍒涘缓铏氭嫙鐜鍠�...
    python -m virtualenv %VENV_DIR%
    if errorlevel 1 (
        echo [閿欒] 鍒涘缓铏氭嫙鐜浠嶇劧澶辫触鍠�...
        echo.
        echo 鎸変换鎰忛敭閫�鍑�...
        pause >nul
        exit /b 1
    )
)
echo [鎴愬姛] 铏氭嫙鐜宸插垱寤哄柕...

:activate_venv
:: 婵�娲昏櫄鎷熺幆澧�
echo [灏濊瘯] 姝ｅ湪婵�娲昏櫄鎷熺幆澧冨柕...

:: 鍐嶆妫�鏌ユ縺娲昏剼鏈槸鍚﹀瓨鍦�
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [璀﹀憡] 铏氭嫙鐜婵�娲昏剼鏈笉瀛樺湪
    echo.
    echo 灏嗙洿鎺ヤ娇鐢ㄧ郴缁� Python 缁х画...
    goto :skip_venv
)

call %VENV_DIR%\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [璀﹀憡] 铏氭嫙鐜婵�娲诲け璐ワ紝灏嗙洿鎺ヤ娇鐢ㄧ郴缁� Python 缁х画鍠�...
    goto :skip_venv
)
echo [鎴愬姛] 铏氭嫙鐜宸叉縺娲诲柕...
goto :install_deps

:skip_venv
echo [灏濊瘯] 灏嗕娇鐢ㄧ郴缁� Python 缁х画杩愯鍠�...

:install_deps
:: 璁剧疆闀滃儚婧愬垪琛�
set "MIRRORS[1]=闃块噷浜戞簮|https://mirrors.aliyun.com/pypi/simple/"
set "MIRRORS[2]=娓呭崕婧恷https://pypi.tuna.tsinghua.edu.cn/simple"
set "MIRRORS[3]=鑵捐婧恷https://mirrors.cloud.tencent.com/pypi/simple"
set "MIRRORS[4]=涓澶ф簮|https://pypi.mirrors.ustc.edu.cn/simple/"
set "MIRRORS[5]=璞嗙摚婧恷http://pypi.douban.com/simple/"
set "MIRRORS[6]=缃戞槗婧恷https://mirrors.163.com/pypi/simple/"

:: 妫�鏌equirements.txt鏄惁瀛樺湪
if not exist requirements.txt (
    echo [璀﹀憡] requirements.txt 鏂囦欢涓嶅瓨鍦紝璺宠繃渚濊禆瀹夎鍠�...
) else (
    :: 瀹夎渚濊禆
    echo [灏濊瘯] 寮�濮嬪畨瑁呬緷璧栧柕...
    
    set SUCCESS=0
    for /L %%i in (1,1,6) do (
        if !SUCCESS! EQU 0 (
            for /f "tokens=1,2 delims=|" %%a in ("!MIRRORS[%%i]!") do (
                echo [灏濊瘯] 浣跨敤%%a瀹夎渚濊禆鍠�...
                pip install -r requirements.txt -i %%b
                if !errorlevel! EQU 0 (
                    echo [鎴愬姛] 浣跨敤%%a瀹夎渚濊禆鎴愬姛锛�
                    set SUCCESS=1
                ) else (
                    echo [澶辫触] %%a瀹夎澶辫触锛屽皾璇曚笅涓�涓簮鍠�...
                    echo 鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�
                )
            )
        )
    )
    
    if !SUCCESS! EQU 0 (
        echo [閿欒] 鎵�鏈夐暅鍍忔簮瀹夎澶辫触锛岃妫�鏌ュ柕锛�
        echo       1. 缃戠粶杩炴帴闂鍠�...
        echo       2. 鎵嬪姩瀹夎锛歱ip install -r requirements.txt鍠�...
        echo       3. 涓存椂鍏抽棴闃茬伀澧�/瀹夊叏杞欢鍠�...
        echo.
        echo 鎸変换鎰忛敭閫�鍑�...
        pause >nul
        exit /b 1
    )
)

:: 妫�鏌ラ厤缃枃浠舵槸鍚﹀瓨鍦�
if not exist run_config_web.py (

    echo [错误] 配置文件 run_config_web.py 不存在，请检查是否解压完整喵...
    echo.
    echo 鎸変换鎰忛敭閫�鍑�...
    pause >nul
    exit /b 1
)

:: 杩愯绋嬪簭
echo [灏濊瘯] 姝ｅ湪鍚姩搴旂敤绋嬪簭鍠�...
python run_config_web.py
set PROGRAM_EXIT_CODE=%errorlevel%

:: 寮傚父閫�鍑哄鐞�
if %PROGRAM_EXIT_CODE% NEQ 0 (
    echo [閿欒] 绋嬪簭寮傚父閫�鍑猴紝閿欒浠ｇ爜: %PROGRAM_EXIT_CODE%...
    echo.
    echo 鍙兘鍘熷洜:
    echo 1. Python妯″潡缂哄け鍠�...
    echo 2. 绋嬪簭鍐呴儴閿欒鍠�...
    echo 3. 鏉冮檺涓嶈冻鍠�...
)

:: 閫�鍑鸿櫄鎷熺幆澧冿紙濡傛灉宸叉縺娲伙級
if exist %VENV_DIR%\Scripts\deactivate.bat (
    echo [灏濊瘯] 姝ｅ湪閫�鍑鸿櫄鎷熺幆澧冨柕...
    call %VENV_DIR%\Scripts\deactivate.bat 2>nul
)
echo [灏濊瘯] 绋嬪簭宸茬粨鏉熷柕...

echo.
echo 鎸変换鎰忛敭閫�鍑哄柕...
pause >nul
exit /b %PROGRAM_EXIT_CODE%
