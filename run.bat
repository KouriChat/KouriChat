@echo off
setlocal enabledelayedexpansion

:: ���ô���ҳΪ GBK
chcp 936 >nul
title My Dream Moments ������

cls
echo ====================================
echo       My Dream Moments ������
echo ====================================
echo.
echo +--------------------------------+
echo ^|   My Dream Moments - AI Chat   ^|
echo ^|   Created with Heart by umaru  ^|
echo +--------------------------------+
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
    echo ��֧�� Python 3.13 �����ϰ汾��
    echo ��ǰPython�汾: !PYTHON_VERSION!
    echo ��ʹ�� Python 3.12 �����汾��
    pause
    exit /b 1
)

:: ���� Python ��������
set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=0"

:: �������⻷��Ŀ¼
set VENV_DIR=.venv

:: ������⻷���Ƿ����
if not exist %VENV_DIR%\Scripts\activate.bat (
    echo �״����У����ڴ������⻷����...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo �������⻷��ʧ����
        pause
        exit /b 1
    )
    :: �������⻷��
    call %VENV_DIR%\Scripts\activate.bat
    
    :: ȷ�� pip �Ѱ�װ������
    echo ���ڸ��� pip...
    python -m pip install --upgrade pip >nul 2>&1
    
    :: �״ΰ�װ����
    if exist requirements.txt (
        echo ���ڰ�װ������...
        :: ���徵��Դ�б�
        set "mirrors[0]=https://mirrors.aliyun.com/pypi/simple/"
        set "mirrors[1]=https://pypi.tuna.tsinghua.edu.cn/simple"
        set "mirrors[2]=https://pypi.mirrors.ustc.edu.cn/simple/"
        set "mirrors[3]=https://mirrors.cloud.tencent.com/pypi/simple"
        set "mirrors[4]=https://pypi.org/simple"

        set success=0
        set mirror_count=5

        :: ����ÿ������Դ
        for /L %%i in (0,1,4) do (
            if !success!==0 (
                echo ����ʹ�þ���Դ: !mirrors[%%i]!
                pip install --no-cache-dir -i !mirrors[%%i]! -r requirements.txt
                if !errorlevel!==0 (
                    set success=1
                    echo ������װ�ɹ���~
                ) else (
                    echo ��ǰ����Դ��װʧ�ܣ�������һ����...
                )
            )
        )

        :: ����Ƿ����о���Դ��ʧ��
        if !success!==0 (
            echo ���о���Դ����װʧ����...
            echo ���飺
            echo 1. ���������Ƿ�����
            echo 2. �ֶ���װ���pip install -r requirements.txt��
            echo 3. �Ƿ��������������
            echo 4. ������ʱ�رշ���ǽ/����
            pause
            exit /b 1
        )
    ) else (
        echo δ�ҵ� requirements.txt �ļ���
        pause
        exit /b 1
    )
) else (
    :: ���⻷���Ѵ��ڣ�ֱ�Ӽ���
    call %VENV_DIR%\Scripts\activate.bat
    echo ��������������...
)

python run_config_web.py

:: ��������쳣�˳�����ͣ��ʾ������Ϣ
if errorlevel 1 (
    echo �������г�����
    pause
)