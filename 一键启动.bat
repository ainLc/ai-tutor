@echo off
chcp 65001 >nul
title AI 私教学习系统
echo ==========================================
echo    AI 私教学习系统 - 启动中...
echo ==========================================
echo.

cd /d "%~dp0"

echo [1/3] 放行防火墙（如已放行会提示已存在，可忽略）...
netsh advfirewall firewall add rule name="ai-tutor-8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
netsh advfirewall firewall add rule name="ai-tutor-5173" dir=in action=allow protocol=TCP localport=5173 >nul 2>&1

echo [2/3] 启动后端 (端口 8000)...
start "AI私教-后端" cmd /k "cd /d %~dp0backend && C:\Users\HS\AppData\Local\Programs\Python\Python312\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo [3/3] 启动前端 (端口 5173)...
start "AI私教-前端" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ==========================================
echo    启动完成！
echo ==========================================
echo.
echo  电脑访问:   http://localhost:5173
echo  手机访问:   http://192.168.1.123:5173
echo             (手机和电脑需连同一个 WiFi)
echo.
echo  两个黑色窗口分别是后端和前端，不要关闭。
echo ==========================================
timeout /t 8 >nul
