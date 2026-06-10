"""网页信息提取服务 — 增强版（支持 Playwright）"""
import time
import random
import logging
import re
import requests
from ..adapters import AdapterRegistry
from ..adapters.generic import GenericAdapter

logger = logging.getLogger(__name__)

TIMEOUT = 30

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

_last_request_time = 0
_request_delay = 0.3

# Playwright 可选
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
    logger.info("Playwright 可用")
except ImportError:
    HAS_PLAYWRIGHT = False


def _get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


def set_delay(seconds):
    global _request_delay
    _request_delay = max(0, seconds)


def fetch_page(url, proxy=None):
    global _last_request_time
    now = time.time()
    wait = _request_delay - (now - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(3):
        try:
            _last_request_time = time.time()
            resp = requests.get(url, headers=_get_headers(), timeout=TIMEOUT,
                                allow_redirects=True, proxies=proxies)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                wait_time = (attempt + 1) * 2
                logger.warning(f"  请求失败 ({attempt+1}/3): {url} — {e}，{wait_time}秒后重试")
                time.sleep(wait_time)
            else:
                raise


def fetch_page_with_js(url, wait_seconds=3):
    """用 Playwright 渲染 JavaScript 后获取页面内容。"""
    if not HAS_PLAYWRIGHT:
        logger.warning("Playwright 不可用，回退到静态抓取")
        return fetch_page(url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(wait_seconds * 1000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logger.warning(f"Playwright 抓取失败: {e}，回退到静态抓取")
        return fetch_page(url)


def extract_play_url_with_js(url):
    """用 Playwright 渲染页面后提取视频 URL（模拟点击播放 + 监听网络）。"""
    if not HAS_PLAYWRIGHT:
        return "", "unknown"

    video_urls = []
    api_urls = []
    video_pattern = re.compile(r"\.(mp4|m3u8|webm|flv)", re.I)
    api_pattern = re.compile(r"(play|video|m3u8|stream|source)", re.I)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def handle_response(response):
                u = response.url
                if video_pattern.search(u):
                    video_urls.append(u)
                elif api_pattern.search(u) and response.status == 200:
                    try:
                        body = response.text()
                        if video_pattern.search(body):
                            api_urls.append((u, body))
                    except:
                        pass

            page.on("response", handle_response)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等页面加载
            page.wait_for_timeout(3000)

            # 尝试点击播放按钮
            play_selectors = [
                "video", ".vjs-big-play-button", ".dplayer-play-icon",
                ".artplayer-icon-play", ".plyr__control--overlaid",
                ".play-btn", ".video-play", "[class*=play]",
                "button[aria-label*=play]", "button[aria-label*=Play]",
                ".fp-play", ".jw-icon-play",
            ]
            for sel in play_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click()
                        page.wait_for_timeout(2000)
                except:
                    pass

            # 等待视频加载
            page.wait_for_timeout(8000)
            browser.close()

        # 优先使用直接捕获的视频 URL
        if video_urls:
            u = video_urls[0]
            return u, _detect_play_type_from_url(u)

        # 回退：从 API 响应中提取
        for api_url, body in api_urls:
            matches = video_pattern.findall(body)
            if matches:
                for m in re.finditer(r'https?://[^\s"\'\']+', body):
                    candidate = m.group(0)
                    if video_pattern.search(candidate):
                        return candidate, _detect_play_type_from_url(candidate)

    except Exception as e:
        logger.warning(f"Playwright 提取失败: {e}")

    return "", "unknown"


def _detect_play_type_from_url(url):
    u = url.lower().split("?")[0]
    if ".m3u8" in u: return "m3u8"
    if ".mp4" in u: return "mp4"
    if ".webm" in u: return "webm"
    if ".flv" in u: return "flv"
    return "unknown"

    video_urls = []
    video_pattern = re.compile(r"\.(mp4|m3u8|webm|flv)", re.I)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 监听网络请求，捕获视频 URL
            def handle_response(response):
                req_url = response.url
                if video_pattern.search(req_url):
                    video_urls.append(req_url)

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)
            browser.close()

        if video_urls:
            url = video_urls[0]
            if ".m3u8" in url:
                return url, "m3u8"
            elif ".mp4" in url:
                return url, "mp4"
            elif ".webm" in url:
                return url, "webm"
            elif ".flv" in url:
                return url, "flv"
            return url, "unknown"

    except Exception as e:
        logger.warning(f"Playwright 提取失败: {e}")

    return "", "unknown"


def extract_items_from_html(html, base_url, adapter_type, selectors):
    adapter = AdapterRegistry.get(adapter_type)
    if not adapter:
        adapter = GenericAdapter()
    return adapter.extract_items(html, base_url, selectors)


def extract_play_url(detail_url, adapter_type, proxy=None):
    adapter = AdapterRegistry.get(adapter_type)
    if not adapter:
        adapter = GenericAdapter()
    try:
        # 先用静态 HTML 提取
        html = fetch_page(detail_url, proxy=proxy)
        url, ptype = adapter.extract_play_url(html, detail_url)

        # Playwright 保留在播放时使用（扫描时不调用，避免太慢）
        # 用户点击播放时可触发 Playwright 提取
        return url, ptype
    except Exception:
        return "", "unknown"
