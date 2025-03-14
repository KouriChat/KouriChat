@echo off
setlocal enabledelayedexpansion

:: 设置代码页为 GBK
chcp 936 >nul
title My Dream Moments 启动器

cls
echo ====================================
echo       My Dream Moments 启动器
echo ====================================
echo.
echo +--------------------------------+
echo ^|   My Dream Moments - AI Chat   ^|
echo ^|   Created with Heart by umaru  ^|
echo +--------------------------------+
echo.

:: 检查 Python 是否已安装
python --version >nul 2>&1
if errorlevel 1 (
    echo Python未安装，请先安装Python
    pause
    exit /b 1
)

:: 检查 Python 版本
for /f "tokens=2" %%I in ('python -V 2^>^&1') do set PYTHON_VERSION=%%I
for /f "tokens=2 delims=." %%I in ("!PYTHON_VERSION!") do set MINOR_VERSION=%%I
if !MINOR_VERSION! GEQ 13 (
    echo 不支持 Python 3.13 及以上版本喵
    echo 当前Python版本: !PYTHON_VERSION!
    echo 请使用 Python 3.12 或更早版本喵
    pause
    exit /b 1
)

:: 设置 Python 环境变量
set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=0"

:: 设置虚拟环境目录
set VENV_DIR=.venv

:: 检查虚拟环境是否存在
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo 首次运行，正在创建虚拟环境喵...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo 创建虚拟环境失败喵
        pause
        exit /b 1
    )
    :: 激活虚拟环境
    call %VENV_DIR%\Scripts\activate.bat
    
    :: 确保 pip 已安装并更新
    echo 正在更新 pip...
    python -m pip install --upgrade pip >nul 2>&1
    
    :: 首次安装依赖
    if exist requirements.txt (
        echo 正在安装依赖喵...
        :: 定义镜像源列表
        set "mirrors[0]=https://mirrors.aliyun.com/pypi/simple/"
        set "mirrors[1]=https://pypi.tuna.tsinghua.edu.cn/simple"
        set "mirrors[2]=https://pypi.mirrors.ustc.edu.cn/simple/"
        set "mirrors[3]=https://mirrors.cloud.tencent.com/pypi/simple"
        set "mirrors[4]=https://pypi.org/simple"

        set success=0
        set mirror_count=5

        :: 尝试每个镜像源
        for /L %%i in (0,1,4) do (
            if !success!==0 (
                echo 尝试使用镜像源: !mirrors[%%i]!
                pip install --no-cache-dir -i !mirrors[%%i]! -r requirements.txt
                if !errorlevel!==0 (
                    set success=1
                    echo 依赖安装成功喵~
                ) else (
                    echo 当前镜像源安装失败，尝试下一个喵...
                )
            )
        )

        :: 检查是否所有镜像源都失败
        if !success!==0 (
            echo 所有镜像源都安装失败喵...
            echo 请检查：
            echo 1. 网络连接是否正常
            echo 2. 手动安装命令：pip install -r requirements.txt喵
            echo 3. 是否存在特殊依赖包
            echo 4. 尝试临时关闭防火墙/代理
            pause
            exit /b 1
        )
    ) else (
        echo 未找到 requirements.txt 文件喵
        pause
        exit /b 1
    )
) else (
    :: 虚拟环境已存在，直接激活
    call %VENV_DIR%\Scripts\activate.bat
    echo 正在启动程序喵...
)

python run_config_web.py

:: 如果发生异常退出则暂停显示错误信息
if errorlevel 1 (
    echo 程序运行出错喵
    pause
)