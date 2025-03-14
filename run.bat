@echo off
setlocal enabledelayedexpansion


:: 璁剧疆浠ｇ爜椤典负 UTF-8
chcp 65001 >nul
title My Dream Moments 鍚姩鍣�

cls
echo ====================================
echo       My Dream Moments 鍚姩鍣�
echo ====================================
echo.
echo ╔═══════════════════════════════════╗
echo ║      My Dream Moments - AI Chat   ║
echo ║      Created with Heart by umaru  ║
echo ╚═══════════════════════════════════╝
echo.


:: 璁剧疆 Python 鐜鍙橀噺
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: 纭繚 pip 宸插畨瑁�
echo cheking pip ...
python -m ensurepip --upgrade >nul 2>&1
if errorlevel 1 (
    echo pip 瀹夎澶辫触鍠�


:: 妫�鏌ヤ緷璧栨槸鍚﹂渶瑕佹洿鏂�
@echo off
setlocal enabledelayedexpansion

:: 璁剧疆浠ｇ爜椤典负 UTF-8
chcp 65001 >nul
title My Dream Moments 鍚姩鍣�

:: ... 鍓嶉潰鐨勪唬鐮佷繚鎸佷笉鍙� ...

:: 妫�鏌ヤ緷璧栨槸鍚﹂渶瑕佹洿鏂�
set "NEEDS_UPDATE=0"
set "req_hash_file=%TEMP%\requirements_hash.txt"
if exist requirements.txt (
    if not exist "%req_hash_file%" set "NEEDS_UPDATE=1"
    if exist "%req_hash_file%" (
        for /f "usebackq" %%a in (`certutil -hashfile requirements.txt SHA256 ^| find /v "hash"`) do (
            set "current_hash=%%a"
        )
        set /p stored_hash=<"%req_hash_file%" 2>nul
        if not "!current_hash!"=="!stored_hash!" set "NEEDS_UPDATE=1"
    )
    
    if "!NEEDS_UPDATE!"=="1" (
        echo 姝ｅ湪瀹夎/鏇存柊渚濊禆鍠�...
        python -m pip install --upgrade pip >nul 2>&1

        :: 瀹氫箟闀滃儚婧愬垪琛�
        set "mirrors[0]=https://pypi.tuna.tsinghua.edu.cn/simple"
        set "mirrors[1]=https://mirrors.aliyun.com/pypi/simple/"
        set "mirrors[2]=https://pypi.mirrors.ustc.edu.cn/simple/"
        set "mirrors[3]=https://mirrors.cloud.tencent.com/pypi/simple"
        set "mirrors[4]=https://pypi.org/simple"

:: 激活虚拟环境
call %VENV_DIR%\Scripts\activate.bat


        :: 灏濊瘯姣忎釜闀滃儚婧�
        for /L %%i in (0,1,4) do (
            if !success!==0 (
                echo 灏濊瘯浣跨敤闀滃儚婧�: !mirrors[%%i]!
                python -m pip install --no-cache-dir -i !mirrors[%%i]! -r requirements.txt
                if !errorlevel!==0 (
                    set success=1
                    echo 渚濊禆瀹夎鎴愬姛鍠祣
                    echo !current_hash!>"%req_hash_file%"
                ) else (
                    echo 褰撳墠闀滃儚婧愬畨瑁呭け璐ワ紝灏濊瘯涓嬩竴涓�...
                )
            )
        )

        :: 妫�鏌ユ槸鍚︽墍鏈夐暅鍍忔簮閮藉け璐�
        if !success!==0 (
            echo 鎵�鏈夐暅鍍忔簮閮藉畨瑁呭け璐ヤ簡鍠�...
            echo 璇锋鏌ョ綉缁滆繛鎺ユ垨鎵嬪姩瀹夎渚濊禆鍠�
            pause
            exit /b 1
        )
    ) else (
        echo 渚濊禆宸叉槸鏈�鏂扮増鏈紝璺宠繃瀹夎鍠�...
    )
)


:: 杩愯绋嬪簭
echo 姝ｅ湪鍚姩绋嬪簭鍠�...
cd /d "%~dp0"
python run_config_web.py

:: 濡傛灉鍙戠敓寮傚父閫�鍑哄垯鏆傚仠鏄剧ず閿欒淇℃伅
if errorlevel 1 (
    echo 绋嬪簭杩愯鍑洪敊鍠�
    pause
)
=======


:: 运行程序
echo 正在启动程序...
python run_config_web.py


:: 异常退出处理
if errorlevel 1 (
    echo 程序异常退出
    pause
)

:: 退出虚拟环境
deactivate
