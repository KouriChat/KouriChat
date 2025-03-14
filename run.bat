@echo off
setlocal enabledelayedexpansion

:: ���ÿ���̨����Ϊ GBK
chcp 936 >nul
title My Dream Moments ������

cls
echo ====================================
echo        My Dream Moments ������
echo ====================================
echo.
echo �X�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�[
echo �U      My Dream Moments - AI Chat   �U
echo �U      Created with Heart by umaru  �U
echo �^�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�a
echo.

:: ��� Python �Ƿ��Ѱ�װ
python --version >nul 2>&1
if errorlevel 1 (
    echo Pythonδ��װ�����Ȱ�װPython
    pause
    exit /b 1
)

:: ��� Python �汾
for /f "tokens=2" %%I in ('python -V 2^>^&1') do set PYTHON_VERSION=%%I
for /f "tokens=2 delims=." %%I in ("!PYTHON_VERSION!") do set MINOR_VERSION=%%I
if !MINOR_VERSION! GEQ 13 (
    echo ��֧�� Python 3.13 �����ϰ汾
    echo ��ǰPython�汾: !PYTHON_VERSION!
    echo ��ʹ�� Python 3.12 �����汾
    pause
    exit /b 1
)

:: �������⻷��Ŀ¼
set VENV_DIR=.venv

:: �������⻷������������ڣ�
if not exist %VENV_DIR% (
    echo ���ڴ������⻷��...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo �������⻷��ʧ��
        pause
        exit /b 1
    )
)

:: �������⻷��
call %VENV_DIR%\Scripts\activate.bat

:: ��װ���������ؾ���Դ���ƣ�
if exist requirements.txt (
    echo ����ʹ���廪����Դ��װ����...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    
    :: ����廪Դʧ�ܣ����԰����ƾ���
    if errorlevel 1 (
        echo �T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T
        echo ���ڳ��԰����ƾ���Դ��װ...
        pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
        
        :: ���������ʧ�ܣ�������Ѷ�ƾ���
        if errorlevel 1 (
            echo �T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T
            echo ���ڳ�����Ѷ�ƾ���Դ��װ...
            pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
            
            :: ����ʧ�ܴ���
            if errorlevel 1 (
                echo �T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T
                echo ���о���Դ����ʧ�ܣ����飺
                echo 1. ���������Ƿ�����
                echo 2. �ֶ���װ���pip install -r requirements.txt
                echo 3. �Ƿ��������������
                echo 4. ������ʱ�رշ���ǽ/����
                pause
                exit /b 1
            )
        )
    )
)

:: ���г���
echo ������������...
python run_config_web.py

:: �쳣�˳�����
if errorlevel 1 (
    echo �����쳣�˳�
    pause
)

:: �˳����⻷��
deactivate
