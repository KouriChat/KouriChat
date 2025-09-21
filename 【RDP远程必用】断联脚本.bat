@echo off
setlocal enabledelayedexpansion

rem 查询 RDP 会话获取目标会话的 ID
for /f "tokens=3" %%a in ('query session ^| findstr /i "rdp-tcp#"') do (
    set session_id=%%a
)

rem 断开 RDP 会话并将连接重定向到控制台
tscon %session_id% /dest:console

endlocal