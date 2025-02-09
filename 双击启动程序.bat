@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================
echo 自动环境配置和程序启动脚本
echo ========================================

REM 获取当前脚本所在的目录（含尾部反斜杠），确保路径不会写死
set "BASE_DIR=%~dp0"
echo [信息] 当前工作目录: %BASE_DIR%
echo.

echo [步骤 1/4] 检查虚拟环境...
REM 检查是否存在虚拟环境，如果不存在则创建
if not exist "%BASE_DIR%venv\Scripts\activate.bat" (
    echo [操作] 未检测到虚拟环境，正在创建...
    python -m venv venv
    if errorlevel 1 (
         echo [错误] 虚拟环境创建失败！
         echo [错误] 请检查Python是否正确安装并配置到环境变量中！
         pause
         exit /b 1
    )
    echo [成功] 虚拟环境创建完成！
) else (
    echo [信息] 检测到已存在的虚拟环境，跳过创建步骤...
)
echo.

echo [步骤 2/4] 激活虚拟环境...
call "%BASE_DIR%venv\Scripts\activate.bat"
echo [成功] 虚拟环境已激活！
echo.

echo [步骤 3/4] 安装依赖包...
echo [信息] 正在通过阿里云镜像源安装必要的依赖包...
echo [安装] 安装 SQLAlchemy...
pip install sqlalchemy -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
echo [安装] 安装 wxauto...
pip install wxauto -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
echo [安装] 安装 openai...
pip install openai -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
echo [安装] 安装 requests...
pip install requests -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
echo [成功] 所有依赖包安装完成！
echo.

REM 如果有 requirements.txt 文件，也可以启用下面的命令统一安装依赖
REM if exist "%BASE_DIR%requirements.txt" (
REM    echo [安装] 从 requirements.txt 安装额外依赖...
REM    pip install -r "%BASE_DIR%requirements.txt" -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
REM )

echo [步骤 4/4] 启动程序...
if exist "%BASE_DIR%bot.py" (
    echo [信息] 找到程序入口文件：bot.py
    echo [启动] 正在启动程序...
    echo ========================================
    "%BASE_DIR%venv\Scripts\python.exe" "%BASE_DIR%bot.py"
) else (
    echo [错误] 未找到程序入口文件！
    echo [错误] 在目录 %BASE_DIR% 中未找到 bot.py
    echo [提示] 请确保 bot.py 与该批处理文件在同一目录下
)

echo.
echo ========================================
echo 程序运行结束，按任意键退出...
pause > nul 