@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   视频聚合搜索播放器（公网 HTTPS）
echo ========================================
echo.
pip install beautifulsoup4 requests -q
echo.
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost
set HOST=0.0.0.0
set PORT=8000
set PUBLIC_TUNNEL=1
echo 本机访问: http://127.0.0.1:8000
echo 正在尝试生成公网 HTTPS 导入地址，请等待控制台输出 https://...trycloudflare.com
echo.
python start.py
pause
