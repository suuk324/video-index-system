#!/usr/bin/env python3
"""一键启动脚本"""
import os
import sys
import sqlite3
import subprocess
import socket
import tempfile
import threading
import traceback
import re

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_ORIGIN_FILE = os.path.join(PROJECT_DIR, "public_origin.txt")
CLOUDFLARED_DIR = os.path.join(PROJECT_DIR, "tools")
CLOUDFLARED_PATH = os.path.join(CLOUDFLARED_DIR, "cloudflared.exe")
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

def check_deps():
    missing = []
    for mod in ["bs4", "requests", "Crypto"]:
        try: __import__(mod)
        except ImportError: missing.append(mod)
    if missing:
        print(f"  缺少依赖: {', '.join(missing)}")
        print(f"  请先运行: pip install beautifulsoup4 requests pycryptodome")
        return False
    # Check Playwright
    try:
        from playwright.sync_api import sync_playwright
        print("  Playwright 可用 — 支持 JavaScript 渲染")
    except ImportError:
        print("  Playwright 不可用 — 静态抓取模式（如需 JS 渲染: pip install playwright && python -m playwright install chromium）")
    print("  依赖已就绪 (beautifulsoup4, requests, pycryptodome)")
    return True


def check_db_path():
    """检测数据库路径是否可用，不可用则换到 /tmp。"""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_dir, "data.db")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS _test (id INTEGER)")
        conn.execute("DROP TABLE IF EXISTS _test")
        conn.commit()
        conn.close()
        return db_path
    except Exception:
        fallback = os.path.join(tempfile.gettempdir(), "video_aggregator_data.db")
        print(f"  注意: 项目目录不可写数据库，改用 {fallback}")
        return fallback


def clear_public_origin():
    os.environ.pop("PUBLIC_ORIGIN", None)
    try:
        os.remove(PUBLIC_ORIGIN_FILE)
    except OSError:
        pass


def save_public_origin(origin):
    public_origin = (origin or "").strip().rstrip("/")
    if not public_origin:
        return
    os.environ["PUBLIC_ORIGIN"] = public_origin
    with open(PUBLIC_ORIGIN_FILE, "w", encoding="utf-8") as fh:
        fh.write(public_origin)


def ensure_cloudflared():
    if os.path.exists(CLOUDFLARED_PATH):
        return CLOUDFLARED_PATH
    import requests
    os.makedirs(CLOUDFLARED_DIR, exist_ok=True)
    print("  正在下载 cloudflared，用于生成公网 HTTPS 地址...")
    resp = requests.get(CLOUDFLARED_URL, timeout=120)
    resp.raise_for_status()
    with open(CLOUDFLARED_PATH, "wb") as fh:
        fh.write(resp.content)
    return CLOUDFLARED_PATH


def start_public_tunnel(port):
    if os.environ.get("PUBLIC_TUNNEL", "0") != "1":
        clear_public_origin()
        return None

    clear_public_origin()
    try:
        cloudflared_path = ensure_cloudflared()
    except Exception as exc:
        print(f"  公网 HTTPS 隧道启动失败: {exc}")
        return None

    print("  正在建立公网 HTTPS 隧道...")
    process = subprocess.Popen(
        [
            cloudflared_path,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--no-autoupdate",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    url_pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com", re.I)

    def watch_output():
        try:
            for line in process.stdout or []:
                match = url_pattern.search(line)
                if match:
                    public_origin = match.group(0).rstrip("/")
                    save_public_origin(public_origin)
                    print(f"  公网 HTTPS: {public_origin}")
        except Exception:
            pass

    threading.Thread(target=watch_output, daemon=True).start()
    return process


def is_port_in_use(host, port):
    test_hosts = [host]
    if host in ("0.0.0.0", "::"):
        test_hosts.extend(["127.0.0.1", "0.0.0.0"])
    for target_host in test_hosts:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                if sock.connect_ex((target_host, port)) == 0:
                    return True
            except OSError:
                continue
    return False


def main():
    print("=" * 40)
    print("  视频聚合搜索播放器")
    print("=" * 40)

    if not check_deps():
        input("\n按回车键退出...")
        sys.exit(1)

    db_path = check_db_path()
    os.environ["DB_PATH"] = db_path

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    sys.path.insert(0, PROJECT_DIR)

    if is_port_in_use(host, port):
        print(f"\n  端口 {port} 已被占用，服务可能已经在运行。")
        print("  请先关闭旧的 start.py 窗口，或结束旧进程后再启动。")
        input("\n按回车键退出...")
        sys.exit(1)

    print(f"\n  启动服务: http://{host}:{port}")
    print(f"  本机访问: http://{browser_host}:{port}")
    print(f"  局域网设备可通过你的电脑 IP + 端口访问")
    print(f"  按 Ctrl+C 停止服务\n")

    tunnel_process = start_public_tunnel(port)

    try:
        import webbrowser
        webbrowser.open(f"http://{browser_host}:{port}")
    except Exception:
        pass

    try:
        from backend.main import run
        run(host=host, port=port)
    except KeyboardInterrupt:
        print("\n  服务已停止")
    except Exception:
        print("\n  启动失败:")
        traceback.print_exc()
    finally:
        if tunnel_process:
            try:
                tunnel_process.terminate()
                tunnel_process.wait(timeout=5)
            except Exception:
                pass
        clear_public_origin()
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()
