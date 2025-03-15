@echo off
setlocal enabledelayedexpansion

:: 设置控制台编码为 GBK
chcp 936 >nul
title My Dream Moments 启动器

cls
echo ====================================
echo        My Dream Moments 启动器
echo ====================================
echo.
echo ╔═══════════════════════════════════╗
echo ║      My Dream Moments - AI Chat                              ║
echo ║       Created with Heart by umaru                              ║
echo ╚═══════════════════════════════════╝
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
    echo 不支持 Python 3.13 及以上版本
    echo 当前Python版本: !PYTHON_VERSION!
    echo 请使用 Python 3.12 及以下版本
    pause
    exit /b 1
)

:: 创建虚拟环境目录
set VENV_DIR=.venv

:: 如果虚拟环境不存在，则创建
if not exist %VENV_DIR% (
    echo 正在创建虚拟环境...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
call %VENV_DIR%\Scripts\activate.bat

:: 安装依赖
if exist requirements.txt (
    echo 使用清华源安装依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo 
        echo 尝试阿里源安装...
        pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
        if errorlevel 1 (
            echo 
            echo 尝试腾讯源安装...
            pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
            if errorlevel 1 (
                echo 
                echo 尝试中科大源安装...
                pip install -r requirements.txt -i https://pypi.mirrors.ustc.edu.cn/simple/
                if errorlevel 1 (
                    echo 
                    echo 尝试豆瓣源安装...
                    pip install -r requirements.txt -i http://pypi.douban.com/simple/
                    if errorlevel 1 (
                        echo 
                        echo 尝试网易源安装...
                        pip install -r requirements.txt -i https://mirrors.163.com/pypi/simple/
                        if errorlevel 1 (
                            echo 
                            echo 所有镜像源安装失败，建议：
                            echo 1. 检查网络连接
                            echo 2. 手动安装命令：pip install -r requirements.txt
                            echo 3. 临时关闭防火墙/代理后重试
                            pause
                            exit /b 1
                        )
                    )
                )
            )
        )
    )
)

:: 启动程序
echo 正在启动应用程序...
python run_config_web.py

:: 异常退出处理
if errorlevel 1 (
    echo 程序异常退出
    pause
)

:: 退出虚拟环境
deactivate
