@echo off
setlocal enabledelayedexpansion

:: 设置控制台编码为 GBK
chcp 936 >nul
title My Dream Moments 启动器

cls
echo ====================================
echo        My Dream Moments Dreamer
echo ====================================
echo.
echo ╔══════════════════════════════════╗
echo ║    My Dream Moments - AI Chat     ║
echo ║    Created with Heart by umaru    ║
echo ╚══════════════════════════════════╝
echo.

:: 添加错误捕获
echo [尝试] 正在启动程序...

:: 检测 Python 是否已安装
echo [检测] 正在检测Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装，请先安装Python
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
    echo [警告] 不支持 Python 3.13 及更高版本
    echo [警告] 请使用 Python 3.12 或更低版本
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
    echo [警告] 虚拟环境似乎已损坏，正在重新创建...
    rmdir /s /q %VENV_DIR% 2>nul
    goto :create_venv
) else (
    goto :activate_venv
)

:create_venv
echo [尝试] 正在创建虚拟环境...
python -m venv %VENV_DIR% 2>nul
if errorlevel 1 (
    echo [错误] 创建虚拟环境失败
    echo.
    echo 可能原因:
    echo 1. Python venv 模块未安装
    echo 2. 权限不足
    echo 3. 磁盘空间不足
    echo.
    echo 尝试安装 venv 模块...
    python -m pip install virtualenv
    if errorlevel 1 (
        echo [错误] 安装 virtualenv 失败
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
    echo [尝试] 使用 virtualenv 创建虚拟环境...
    python -m virtualenv %VENV_DIR%
    if errorlevel 1 (
        echo [错误] 创建虚拟环境仍然失败
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
)
echo [成功] 虚拟环境已创建

:activate_venv
:: 激活虚拟环境
echo [尝试] 正在激活虚拟环境...

:: 再次检查激活脚本是否存在
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [警告] 虚拟环境激活脚本不存在
    echo.
    echo 将直接使用系统 Python 继续...
    goto :skip_venv
)

call %VENV_DIR%\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [警告] 虚拟环境激活失败，将直接使用系统 Python 继续...
    goto :skip_venv
)
echo [成功] 虚拟环境已激活
goto :install_deps

:skip_venv
echo [尝试] 将使用系统 Python 继续运行

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
    echo [警告] requirements.txt 文件不存在，跳过依赖安装
) else (
    :: 安装依赖
    echo [尝试] 开始安装依赖...
    
    set SUCCESS=0
    for /L %%i in (1,1,6) do (
        if !SUCCESS! EQU 0 (
            for /f "tokens=1,2 delims=|" %%a in ("!MIRRORS[%%i]!") do (
                echo [尝试] 使用%%a安装依赖...
                pip install -r requirements.txt -i %%b
                if !errorlevel! EQU 0 (
                    echo [成功] 使用%%a安装依赖成功！
                    set SUCCESS=1
                ) else (
                    echo [失败] %%a安装失败，尝试下一个源
                    echo ──────────────────────────────────────────────────────
                )
            )
        )
    )
    
    if !SUCCESS! EQU 0 (
        echo [错误] 所有镜像源安装失败，请检查：
        echo       1. 网络连接问题
        echo       2. 手动安装：pip install -r requirements.txt
        echo       3. 临时关闭防火墙/安全软件
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
)

:: 检查配置文件是否存在
if not exist run_config_web.py (
    echo [错误] 配置文件 run_config_web.py 不存在
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

:: 运行程序
echo [尝试] 正在启动应用程序...
python run_config_web.py
set PROGRAM_EXIT_CODE=%errorlevel%

:: 异常退出处理
if %PROGRAM_EXIT_CODE% NEQ 0 (
    echo [错误] 程序异常退出，错误代码: %PROGRAM_EXIT_CODE%
    echo.
    echo 可能原因:
    echo 1. Python模块缺失
    echo 2. 程序内部错误
    echo 3. 权限不足
)

:: 退出虚拟环境（如果已激活）
if exist %VENV_DIR%\Scripts\deactivate.bat (
    echo [尝试] 正在退出虚拟环境...
    call %VENV_DIR%\Scripts\deactivate.bat 2>nul
)
echo [尝试] 程序已结束

echo.
echo 按任意键退出...
pause >nul
exit /b %PROGRAM_EXIT_CODE%