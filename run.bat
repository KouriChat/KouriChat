@echo off
setlocal enabledelayedexpansion

:: ���ÿ���̨����Ϊ GBK
chcp 936 >nul
title My Dream Moments ������

:: ���þ���Դ�б�
set "MIRRORS[1]=������Դ|https://mirrors.aliyun.com/pypi/simple/"
set "MIRRORS[2]=�廪Դ|https://pypi.tuna.tsinghua.edu.cn/simple"
set "MIRRORS[3]=��ѶԴ|https://mirrors.cloud.tencent.com/pypi/simple"
set "MIRRORS[4]=�пƴ�Դ|https://pypi.mirrors.ustc.edu.cn/simple/"
set "MIRRORS[5]=����Դ|http://pypi.douban.com/simple/"
set "MIRRORS[6]=����Դ|https://mirrors.163.com/pypi/simple/"

cls
echo ====================================
echo        My Dream Moments Dreamer
echo ====================================
echo.
echo �X�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�[
echo �U    My Dream Moments - AI Chat     �U
echo �U    Created with Heart by umaru    �U
echo �^�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�a
echo.

:: ��Ӵ��󲶻�
echo [����] ��������������...

:: ��� Python �Ƿ��Ѱ�װ
echo [���] ���ڼ��Python������...
python --version >nul 2>&1
if errorlevel 1 (
    echo [����] Pythonδ��װ�����Ȱ�װPython��...
    echo.
    echo ��������˳�...
    pause >nul
    exit /b 1
)

:: ��� Python �汾
for /f "tokens=2" %%I in ('python -V 2^>^&1') do set PYTHON_VERSION=%%I
echo [����] ��⵽Python�汾��: !PYTHON_VERSION!
for /f "tokens=2 delims=." %%I in ("!PYTHON_VERSION!") do set MINOR_VERSION=%%I
if !MINOR_VERSION! GEQ 13 (
    echo [����] ��֧�� Python 3.13 �����߰汾��...
    echo [����] ��ʹ�� Python 3.12 ����Ͱ汾��...
    echo.
    echo ��������˳���...
    pause >nul
    exit /b 1
)

:: �������⻷��Ŀ¼
set VENV_DIR=.venv

:: ����PIP����
set PYTHONIOENCODING=utf-8
set PIP_NO_CACHE_DIR=off

:: ������⻷�������ڻ򼤻�ű������ڣ������´���
if not exist %VENV_DIR% (
    goto :create_venv
) else if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [����] ���⻷���ƺ����𻵣��������´�����...
    rmdir /s /q %VENV_DIR% 2>nul
    goto :create_venv
) else (
    goto :activate_venv
)

:create_venv
echo [����] ���ڴ������⻷��...
python -m venv %VENV_DIR% 2>nul
if errorlevel 1 (
    echo [����] �������⻷��ʧ����...
    echo.
    echo ����ԭ����:
    echo 1. Python venv ģ��δ��װ��...
    echo 2. Ȩ�޲�����...
    echo 3. ���̿ռ䲻����...
    echo.
    echo ���԰�װ venv ģ��...
    python -m pip install virtualenv
    if errorlevel 1 (
        echo [����] ��װ virtualenv ʧ����...
        echo.
        echo ��������˳���...
        pause >nul
        exit /b 1
    )
    echo [����] ʹ�� virtualenv �������⻷��...
    python -m virtualenv %VENV_DIR%
    if errorlevel 1 (
        echo [����] �������⻷����Ȼʧ����...
        echo.
        echo ��������˳���...
        pause >nul
        exit /b 1
    )
)
echo [�ɹ�] ���⻷���Ѵ�����...

:activate_venv
:: �������⻷��
echo [����] ���ڼ������⻷����...

:: �ٴμ�鼤��ű��Ƿ����
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo [����] ���⻷������ű���������...
    echo.
    echo ��ֱ��ʹ��ϵͳ Python ������...
    goto :skip_venv
)

call %VENV_DIR%\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [����] ���⻷������ʧ�ܣ���ֱ��ʹ��ϵͳ Python ������...
    goto :skip_venv
)
echo [�ɹ�] ���⻷���Ѽ�����...

:: ����pip
echo [����] ��������pip��...

set PIP_UPGRADED=0
for /L %%i in (1,1,6) do (
    if !PIP_UPGRADED! EQU 0 (
        for /f "tokens=1,2 delims=|" %%a in ("!MIRRORS[%%i]!") do (
            echo [����] ʹ��%%a����pip...
            python -m pip install --upgrade pip -i %%b
            if !errorlevel! EQU 0 (
                echo [�ɹ�] ʹ��%%a����pip�ɹ���
                set PIP_UPGRADED=1
                goto :pip_upgrade_done
            ) else (
                echo [ʧ��] ʹ��%%a����pipʧ�ܣ�������һ��Դ
            )
        )
    )
)

:pip_upgrade_done
if !PIP_UPGRADED! EQU 0 (
    echo [����] ���о���Դ����pipʧ�ܣ�����ֱ������...
    python -m pip install --upgrade pip
    if !errorlevel! NEQ 0 (
        echo [����] ����pipʧ�ܣ�����ʹ�õ�ǰ�汾...
    ) else (
        echo [�ɹ�] ֱ������pip�ɹ���
    )
) else (
    echo [�ɹ�] pip���������...
)

goto :install_deps

:skip_venv
echo [����] ��ʹ��ϵͳ Python ����������...

:install_deps
:: ���requirements.txt�Ƿ����
if not exist requirements.txt (
    echo [����] requirements.txt �ļ������ڣ�����������װ��...
) else (
    :: ��װ����
    echo [����] ��ʼ��װ������...
    
    :: ����UTF-8��ʽ����ʱrequirements�ļ�
    echo [����] ���ڴ���UTF-8��ʽ��requirements�ļ���...
    powershell -Command "Get-Content -Path requirements.txt -Encoding Default | Set-Content -Path requirements_utf8.txt -Encoding UTF8"
    if !errorlevel! NEQ 0 (
        echo [����] ת��requirements.txt����ʧ�ܣ�����ֱ�Ӱ�װ��...
        copy /Y requirements.txt requirements_utf8.txt >nul
    )
    
    set SUCCESS=0
    for /L %%i in (1,1,6) do (
        if !SUCCESS! EQU 0 (
            for /f "tokens=1,2 delims=|" %%a in ("!MIRRORS[%%i]!") do (
                echo [����] ʹ��%%a��װ����...
                set "PIP_CONFIG_FILE="
                pip --no-cache-dir install -r requirements_utf8.txt -i %%b
                if !errorlevel! EQU 0 (
                    echo [�ɹ�] ʹ��%%a��װ�����ɹ���
                    set SUCCESS=1
                ) else (
                    echo [ʧ��] %%a��װʧ�ܣ�������һ��Դ
                    echo ������������������������������������������������������������������������������������������������������������
                )
            )
        )
    )
    
    :: ������ʱ�ļ�
    if exist requirements_utf8.txt del /f /q requirements_utf8.txt
    
    if !SUCCESS! EQU 0 (
        echo [����] ���о���Դ��װʧ�ܣ����飺
        echo       1. ������������
        echo       2. �ֶ���װ��pip install -r requirements.txt
        echo       3. ��ʱ�رշ���ǽ/��ȫ���
        echo.
        echo [����] ����ʹ��UTF-8����ֱ�Ӱ�װ...
        python -X utf8 -m pip install -r requirements.txt
        if !errorlevel! EQU 0 (
            echo [�ɹ�] UTF-8ģʽ��װ�ɹ���
            set SUCCESS=1
        ) else (
            echo ��������˳�...
            pause >nul
            exit /b 1
        )
    )
)

:: ��������ļ��Ƿ����
if not exist run_config_web.py (
    echo [����] �����ļ� run_config_web.py ��������...
    echo.
    echo ��������˳���...
    pause >nul
    exit /b 1
)

:: ���г���
echo [����] ��������Ӧ�ó�����...
python -X utf8 run_config_web.py
set PROGRAM_EXIT_CODE=%errorlevel%

:: �쳣�˳�����
if %PROGRAM_EXIT_CODE% NEQ 0 (
    echo [����] �����쳣�˳����������: %PROGRAM_EXIT_CODE%��...
    echo.
    echo ����ԭ��:
    echo 1. Pythonģ��ȱʧ��...
    echo 2. �����ڲ�������...
    echo 3. Ȩ�޲�����...
)

:: �˳����⻷��������Ѽ��
if exist %VENV_DIR%\Scripts\deactivate.bat (
    echo [����] �����˳����⻷����...
    call %VENV_DIR%\Scripts\deactivate.bat 2>nul
)
echo [����] �����ѽ�����...

echo.
echo ��������˳���...
pause >nul
exit /b %PROGRAM_EXIT_CODE%