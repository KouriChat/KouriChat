@echo off
REM ���ô���ҳΪ GBK
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

REM ���û���������֧������·��
set PYTHONIOENCODING=utf8
set JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8

REM ���·���Ƿ��������
echo %CD% | findstr /R /C:"[^\x00-\x7F]" >nul
if not errorlevel 1 (
    echo [����] ��ǰ·�����������ַ������ܻᵼ�����⣡
    echo ��ǰ·��: %CD%
    echo ���齫�����ƶ�����Ӣ��·�������С�
    echo.
    choice /c yn /m "�Ƿ��������"
    if errorlevel 2 exit /b 1
)

REM ��� Python ����
where python >nul 2>nul
if errorlevel 1 (
    echo [����] δ��⵽ Python ������
    echo �밲װ Python ��ȷ��������ӵ�ϵͳ���������С�
    echo ��������˳�...
    pause >nul
    exit /b 1
)

REM ��� Python �汾
python --version | findstr "3." >nul
if errorlevel 1 (
    echo [����] Python �汾�����ݣ�
    echo �밲װ Python 3.x �汾��
    echo ��������˳�...
    pause >nul
    exit /b 1
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

REM �޸� pip ��װ���������β���
:install_modules
echo ���ڼ���Ҫ�� Python ģ��...
set modules=pyautogui streamlit sqlalchemy
for %%m in (%modules%) do (
    python -c "import %%m" 2>nul
    if errorlevel 1 (
        echo ���ڰ�װ %%m ģ��...
        pip install --no-warn-script-location --disable-pip-version-check ^
            --trusted-host pypi.org ^
            --trusted-host files.pythonhosted.org ^
            --trusted-host mirrors.aliyun.com ^
            %%m -i http://mirrors.aliyun.com/pypi/simple/
        if errorlevel 1 (
            echo [����] %%m ģ�鰲װʧ�ܣ�
            echo ���Թ���Ա������л��ֶ���װ��ģ�顣
            choice /c yn /m "�Ƿ��������"
            if errorlevel 2 exit /b 1
        )
    )
)

echo ģ������ɣ�
echo.

REM �޸�������ʽ�������� Python ʹ�� UTF-8
echo �����������ý���...
if not exist "run_config_web.py" (
    echo [����] δ�ҵ� run_config_web.py �ļ���
    echo ��ȷ�����ļ������ڵ�ǰĿ¼��
    pause
    exit /b 1
)

REM ���� Python �ű�ʱ���� UTF-8
start http://localhost:8501/
start /b cmd /c "set PYTHONIOENCODING=utf8 && python run_config_web.py"
if errorlevel 1 (
    echo [����] ���ý�������ʧ�ܣ�
    echo ���� run_config_web.py �Ƿ����﷨����
    pause
    exit /b 1
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
    cmd /c "set PYTHONIOENCODING=utf8 && python run.py"
    if errorlevel 1 (
        echo [31m[����][0m ����������ʧ�ܣ�
        echo ��ȷ�� run.py �ļ����������﷨����
        pause
        exit /b 1
    )
) else if /i "%CONFIG_DONE%"=="N" (
    goto check_config
) else (
    echo ��Ч�����룬������ Y �� N
    goto check_config
)

pause