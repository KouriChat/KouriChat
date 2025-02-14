@echo off
chcp 936
title My Dream Moments ������

cls
echo ====================================
echo        My Dream Moments ������
echo ====================================
echo.
echo �X�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�[
echo �U          My Dream Moments - AI Chat          �U
echo �U            Created with Heart by umaru       �U
echo �^�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�a
echo.

REM ���������ݷ�ʽ
set "SCRIPT_PATH=%~f0"
set "DESKTOP_PATH=%USERPROFILE%\Desktop"
set "SHORTCUT_PATH=%DESKTOP_PATH%\My Dream Moments.lnk"

dir "%SHORTCUT_PATH%" >nul 2>nul
if errorlevel 1 (
    choice /c yn /m "�Ƿ�Ҫ�����洴����ݷ�ʽ"
    if errorlevel 2 goto SKIP_SHORTCUT
    if errorlevel 1 (
        echo ���ڴ��������ݷ�ʽ...
        powershell "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%SHORTCUT_PATH%'); $SC.TargetPath = '%SCRIPT_PATH%'; $SC.WorkingDirectory = '%~dp0'; $SC.Save()"
        echo ��ݷ�ʽ������ɣ�
        echo.
    )
)
:SKIP_SHORTCUT

where python >nul 2>nul
if errorlevel 1 (
    echo ����ϵͳ��δ�ҵ�Python��
    echo ��ȷ���Ѱ�װPython����ӵ�ϵͳ���������С�
    pause
    exit
)

echo ���ڼ���Ҫ��Pythonģ��...
python -c "import pyautogui" 2>nul
if errorlevel 1 (
    echo ���ڰ�װ pyautogui ģ��...
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host mirrors.aliyun.com pyautogui -i http://mirrors.aliyun.com/pypi/simple/
)

python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo ���ڰ�װ streamlit ģ��...
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host mirrors.aliyun.com streamlit -i http://mirrors.aliyun.com/pypi/simple/
)

python -c "import sqlalchemy" 2>nul
if errorlevel 1 (
    echo ���ڰ�װ sqlalchemy ģ��...
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host mirrors.aliyun.com sqlalchemy -i http://mirrors.aliyun.com/pypi/simple/
)

echo ģ������ɣ�
echo.

echo �����������ý���...
start http://localhost:8501/
start /b python run_config_web.py
if errorlevel 1 (
    echo ���ý�������ʧ�ܣ�
    echo ��ȷ��run_config_web.py�ļ����ڡ�
    pause
    exit
)

echo ���ڵȴ����ý�������...
timeout /t 5 /nobreak >nul

:check_config
echo.
echo �Ƿ�����������޸ģ�(Y/N)
set /p CONFIG_DONE=": "
if /i "%CONFIG_DONE%"=="Y" (
    taskkill /f /im python.exe >nul 2>nul
    echo.
    echo ������ɣ���������������...
    python run.py
    if errorlevel 1 (
        echo ����������ʧ�ܣ�
        echo ��ȷ��run.py�ļ����ڡ�
        pause
        exit
    )
) else if /i "%CONFIG_DONE%"=="N" (
    goto check_config
) else (
    echo ��Ч�����룬������ Y �� N
    goto check_config
)

pause