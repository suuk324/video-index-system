@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   视频聚合搜索播放器
echo ========================================
echo.
pip install beautifulsoup4 requests -q
echo.
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost
set HOST=0.0.0.0
set PORT=9000
echo 服务启动在端口 9000 ...
echo 本机请访问 http://127.0.0.1:9000
echo 局域网设备请访问 你的电脑IP:9000
echo.
python start.py
pause
