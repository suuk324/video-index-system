"""HTTP 服务器主入口 — ThreadingHTTPServer 支持并发"""
import os
import json
import logging
import mimetypes
from socketserver import ThreadingMixIn
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from .database import init_db
from . import api_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.directory = FRONTEND_DIR
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if path.startswith("/api/"):
            return self._handle_api("GET", path, params)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        body = self._read_body()
        return self._handle_api("POST", path, params, body)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        body = self._read_body()
        return self._handle_api("PUT", path, params, body)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        return self._handle_api("DELETE", path, params)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            raw = self.rfile.read(length)
            try: return json.loads(raw)
            except: return {}
        return {}

    def _handle_api(self, method, path, params, body=None):
        try:
            result = api_handler.dispatch(method, path, params, body or {})
            if len(result) == 3:
                status, data, meta = result
            else:
                status, data = result
                meta = None
            if meta:
                self._send_raw(status, data, meta)
            else:
                self._send_json(status, data)
        except Exception as e:
            logger.error(f"API error: {method} {path} — {e}", exc_info=True)
            self._send_json(500, {"detail": str(e)})

    def _send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_raw(self, status, data, meta):
        payload = data if isinstance(data, bytes) else str(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", meta.get("content_type", "text/plain; charset=utf-8"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        for key, value in (meta.get("headers") or {}).items():
            self.send_header(str(key), str(value))
        filename = meta.get("filename", "")
        if filename:
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} — {format % args}")


def run(host="0.0.0.0", port=8000):
    init_db()
    logger.info("数据库初始化完成")
    from .scheduler import start_scheduler
    start_scheduler()
    server = ThreadingHTTPServer((host, port), AppHandler)
    logger.info(f"服务启动: http://{host}:{port} (多线程模式)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务停止")
    finally:
        from .scheduler import stop_scheduler
        stop_scheduler()
        server.server_close()
