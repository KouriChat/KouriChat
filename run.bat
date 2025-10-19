@echo off
setlocal enabledelayedexpansion

:: 设置控制台编码为 GBK
chcp 936 >nul
title KouriChat 启动器

cls
echo ====================================
echo         K O U R I   C H A T
echo ====================================
echo.
echo ╔══════════════════════════════════╗
echo ║       KouriChat - AI Chat        ║
echo ║  Created with Heart by KouriTeam ║
echo ╚══════════════════════════════════╝
echo KouriChat - AI Chat  Copyright (C) 2025, DeepAnima Network Technology Studio
echo.

:: 添加错误捕获
echo [尝试] 正在启动程序喵...

:: 检测 Python 是否已安装
echo [检测] 正在检测Python环境喵...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装，请先安装Python喵...   
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

:: 检测 Python 版本
for /f "tokens=2" %%I in ('python -V 2^>^&1') do set PYTHON_VERSION=%%I
echo [尝试] 检测到Python版本: !PYTHON_VERSION!
for /f "tokens=2 delims=." %%I in ("!PYTHON_VERSION!") do set MINOR_VERSION=%%I
if !MINOR_VERSION! GEQ 13 (
    echo [警告] 不支持 Python 3.12 及更高版本喵...
    echo [警告] 请使用 Python 3.11 或更低版本喵...
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

:: 设置虚拟环境目录
set VENV_DIR=.venv

:: 如果虚拟环境不存在或激活脚本不存在，则重新创建
if not exist %VENV_DIR% (
    goto :create_venv
) else if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [警告] 虚拟环境似乎已损坏，正在重新创建喵...
    rmdir /s /q %VENV_DIR% 2>nul
    goto :create_venv
) else (
    goto :activate_venv
)

:create_venv
echo [尝试] 正在创建虚拟环境喵...
python -m venv %VENV_DIR% 2>nul
if errorlevel 1 (
    echo [错误] 创建虚拟环境失败喵...
    echo.
    echo 可能原因:
    echo 1. Python venv 模块未安装喵...
    echo 2. 权限不足喵...
    echo 3. 磁盘空间不足喵...
    echo.
    echo 尝试安装 venv 模块喵...
    python -m pip install virtualenv
    if errorlevel 1 (
        echo [错误] 安装 virtualenv 失败
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
    echo [尝试] 使用 virtualenv 创建虚拟环境喵...
    python -m virtualenv %VENV_DIR%
    if errorlevel 1 (
        echo [错误] 创建虚拟环境仍然失败喵...
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
)
echo [成功] 虚拟环境已创建喵...

:activate_venv
:: 激活虚拟环境
echo [尝试] 正在激活虚拟环境喵...

:: 再次检查激活脚本是否存在
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [警告] 虚拟环境激活脚本不存在
    echo.
    echo 将直接使用系统 Python 继续...
    goto :skip_venv
)

call %VENV_DIR%\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [警告] 虚拟环境激活失败，将直接使用系统 Python 继续喵...
    goto :skip_venv
)
echo [成功] 虚拟环境已激活喵...
goto :install_deps

:skip_venv
echo [尝试] 将使用系统 Python 继续运行喵...

:install_deps
:: 设置镜像源列表
set "MIRRORS[1]=阿里云源|https://mirrors.aliyun.com/pypi/simple/"
set "MIRRORS[2]=清华源|https://pypi.tuna.tsinghua.edu.cn/simple"
set "MIRRORS[3]=腾讯源|https://mirrors.cloud.tencent.com/pypi/simple"
set "MIRRORS[4]=中科大源|https://pypi.mirrors.ustc.edu.cn/simple/"
set "MIRRORS[5]=豆瓣源|http://pypi.douban.com/simple/"
set "MIRRORS[6]=网易源|https://mirrors.163.com/pypi/simple/"

:: 检查requirements.txt是否存在
if not exist requirements.txt (
    echo [警告] requirements.txt 文件不存在，跳过依赖安装喵...
) else (
    :: 安装依赖
    echo [尝试] 开始安装依赖喵...
    
    set SUCCESS=0
    for /L %%i in (1,1,6) do (
        if !SUCCESS! EQU 0 (
            for /f "tokens=1,2 delims=|" %%a in ("!MIRRORS[%%i]!") do (
                echo [尝试] 使用%%a安装依赖喵...
                pip install -r requirements.txt -i %%b
                if !errorlevel! EQU 0 (
                    echo [成功] 使用%%a安装依赖成功！
                    set SUCCESS=1
                ) else (
                    echo [失败] %%a安装失败，尝试下一个源喵...
                    echo ──────────────────────────────────────────────────────
                )
            )
        )
    )
    
    if !SUCCESS! EQU 0 (
        echo [错误] 所有镜像源安装失败，请检查喵：
        echo       1. 网络连接问题喵...
        echo       2. 手动安装：pip install -r requirements.txt喵...
        echo       3. 临时关闭防火墙/安全软件喵...
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
)

:: 检查配置文件是否存在
if not exist run_config_web.py (
    echo [错误] 配置文件 run_config_web.py 不存在喵...
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

:: 运行程序
echo [尝试] 正在启动应用程序喵...
python run_config_web.py
set PROGRAM_EXIT_CODE=%errorlevel%

:: 异常退出处理
if %PROGRAM_EXIT_CODE% NEQ 0 (
    echo [错误] 程序异常退出，错误代码: %PROGRAM_EXIT_CODE%...
    echo.
    echo 可能原因:
    echo 1. Python模块缺失喵...
    echo 2. 程序内部错误喵...
    echo 3. 权限不足喵...
)

:: 退出虚拟环境（如果已激活）
if exist %VENV_DIR%\Scripts\deactivate.bat (
    echo [尝试] 正在退出虚拟环境喵...
    call %VENV_DIR%\Scripts\deactivate.bat 2>nul
)
echo [尝试] 程序已结束喵...

echo.
echo 按任意键退出喵...
pause >nul
exit /b %PROGRAM_EXIT_CODE%
