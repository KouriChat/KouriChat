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
set "python_home="

:: ���ȼ�鵱ǰĿ¼
if exist "Python310" (
    set "python_home=%cd%\Python310"
    goto :python_found
)

:: �����֪�� Python310 ����ļ�
if exist "%python_installed_flag%" (
    set /p python_home=<"%python_installed_flag%"
    if exist "!python_home!" goto :python_found
)

:: ���û���ҵ� Python310����װ
echo δ�ҵ� Python310 ��������ʼ��װ...
start /wait Python310.exe
set "python_home=%cd%\Python310"
echo !python_home!>"%python_installed_flag%"

:python_found
echo ʹ�� Python ����: !python_home!

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
set VENV_DIR=.venv

:: ������⻷���Ƿ����
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

:: ��װ����
if exist requirements.txt (
    echo ���ڰ�װ����...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ��װ����ʧ��
        pause
        exit /b 1
    )
)

:: ���г���
echo ������������...
python run_config_web.py

:: ��������쳣�˳�����ͣ��ʾ������Ϣ
if errorlevel 1 (
    echo �������г���
    pause
)

:: �˳����⻷��
deactivate