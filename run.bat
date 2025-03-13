@echo off
setlocal enabledelayedexpansion

:: ���ô���ҳΪ GBK
chcp 936 >nul
title My Dream Moments ������

cls
echo ====================================
echo        My Dream Moments ������
echo ====================================
echo.
echo �X�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�[
echo �U      My Dream Moments - AI Chat   �U
echo �U      Created with Heart by umaru  �U
echo �^�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�a
echo.

:: ����Ƿ���� Python310 ��������ļ�
set "python_installed_flag=%USERPROFILE%\.python310_installed"
set "python_home=%~dp0Python310"

:: ���û���ҵ� Python310����װ
if not exist "%python_home%\python.exe" (
    echo δ�ҵ� Python 3.10 ��������ʼ��װ...
    if exist "Python310.exe" (
        echo ���ڰ�װ Python 3.10...
        start /wait Python310.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 TargetDir="%python_home%"
        echo !python_home!>"%python_installed_flag%"
    ) else (
        echo ����δ�ҵ� Python310.exe ��װ����
        pause
        exit /b 1
    )
)

:python_found
echo ʹ�� Python ����: !python_home!

:: ���� Python ��������
set "PYTHON_HOME=!python_home!"
set "PYTHONPATH=!python_home!\Lib;!python_home!\DLLs;!python_home!\Lib\site-packages"
set "PATH=!python_home!;!python_home!\Scripts;%PATH%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: �޸�/���°�װ pip
echo �����޸� pip ��װ...
powershell -Command "(New-Object Net.WebClient).DownloadFile('https://mirrors.aliyun.com/pypi/get-pip.py', 'get-pip.py')"
"!python_home!\python.exe" get-pip.py --force-reinstall --no-warn-script-location
del /f /q get-pip.py

:: ���� pip ʹ���廪Դ
if not exist "%APPDATA%\pip" mkdir "%APPDATA%\pip"
(
echo [global]
echo index-url = https://pypi.tuna.tsinghua.edu.cn/simple
echo [install]
echo trusted-host = mirrors.aliyun.com
) > "%APPDATA%\pip\pip.ini"

:: �����ؽ� Python ����
echo �������� Python ����...
if exist "!python_home!\Lib\site-packages" rd /s /q "!python_home!\Lib\site-packages"
if exist "!python_home!\Scripts" rd /s /q "!python_home!\Scripts"

:: ���� Python �����ļ�
if exist "%~dp0*.pyc" del /f /q "%~dp0*.pyc"
if exist "%~dp0__pycache__" rd /s /q "%~dp0__pycache__"

:: ��֤ Python ��װ��ʹ������·����
"!python_home!\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo Python�����쳣�����鰲װ
    echo ��ǰ Python ·��: !python_home!
    echo ��������: "!python_home!\python.exe" --version
    pause
    exit /b 1
)

:: ȷ�� PATH �а��� Python �� pip
set "PATH=!python_home!;!python_home!\Scripts;%PATH%"

:: ������ʱ��������
set "path=!python_home!;!python_home!\Scripts;!path!"

:: ��֤ Python ��װ
python --version >nul 2>&1
if errorlevel 1 (
    echo Python�����쳣�����鰲װ
    pause
    exit /b 1
)

:: �������⻷��Ŀ¼
set VENV_DIR=%python_home%\.venv

:: ������⻷���Ƿ����
if not exist %VENV_DIR% (
    echo ���ڴ������⻷��...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo �������⻷��ʧ��
        pause
        exit /b 1
    )
    set "FRESH_ENV=1"
)

:: �������⻷��
call %VENV_DIR%\Scripts\activate.bat

:: ȷ�� pip �Ѱ�װ
echo ���ڼ�� pip...
python -m ensurepip --upgrade
if errorlevel 1 (
    echo pip ��װʧ��
    pause
    exit /b 1
)

:: ��������Ƿ���Ҫ����
set "NEEDS_UPDATE=0"
if exist requirements.txt (
    if not exist "%req_hash_file%" set "NEEDS_UPDATE=1"
    if exist "%req_hash_file%" (
        for /f "usebackq" %%a in (`certutil -hashfile requirements.txt SHA256 ^| find /v "hash"`) do (
            set "current_hash=%%a"
        )
        set /p stored_hash=<"%req_hash_file%"
        if not "!current_hash!"=="!stored_hash!" set "NEEDS_UPDATE=1"
    )
    
    if "!NEEDS_UPDATE!"=="1" (
        echo ���ڰ�װ/��������...
        python -m pip install --upgrade pip
        python -m pip install --no-cache-dir -r requirements.txt
        if errorlevel 1 (
            echo ��װ����ʧ��
            pause
            exit /b 1
        )
        echo !current_hash!>"%req_hash_file%"
    ) else (
        echo �����������°汾��������װ...
    )
)

:: ���г���
echo ������������...
cd /d "%~dp0"
python run_config_web.py

:: ��������쳣�˳�����ͣ��ʾ������Ϣ
if errorlevel 1 (
    echo �������г���
    pause
)

:: �˳����⻷��
deactivate