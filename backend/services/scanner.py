"""扫描调度逻辑 — 并发爬取、智能翻页、可停止"""
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, urlunparse
from bs4 import BeautifulSoup
from ..database import get_source, get_sources, upsert_video, auto_extract_tags
from .extractor import fetch_page, extract_items_from_html, extract_play_url

logger = logging.getLogger(__name__)

STATIC_EXT = re.compile(
    r'\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|zip|rar|pdf|doc|xls)'
    r'(\?|$)', re.I
)

# 非内容页前缀（扫描时跳过）
SKIP_PREFIXES = (
    "/author/", "/category/", "/tag/", "/tags/", "/page/",
    "/wp-admin/", "/wp-login", "/wp-content/", "/wp-includes/",
    "/feed/", "/comment", "/search/", "/user/", "/profile/",
    "/login", "/register", "/about", "/contact", "/privacy",
    "/terms", "/cdn-cgi/", "/.well-known/", "/wp-json/",
)

# 翻页关键词
NEXT_PAGE_PATTERNS = [
    re.compile(r'下[一一页页]', re.I),
    re.compile(r'next', re.I),
    re.compile(r'›'),
    re.compile(r'»'),
    re.compile(r'>'),
]

DEFAULT_MAX_PAGES = 5000
CONCURRENCY = 5  # 并发线程数

_status = {
    "running": False, "source_name": "",
    "pages_crawled": 0, "videos_found": 0,
    "new_added": 0, "updated": 0,
    "stopped": False, "done": False, "error": "",
}
_status_lock = threading.Lock()
_stop_flag = threading.Event()


def normalize_url(url):
    parsed = urlparse(url)
    normalized = parsed._replace(
        fragment="",
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
    )
    return urlunparse(normalized)


def normalize_item_url(url):
    parsed = urlparse(url)
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
    )
    return urlunparse(normalized)


def needs_cover_fallback(url):
    lower = (url or "").lower()
    if not lower:
        return True
    return any(token in lower for token in (
        "social-default", "banner", "avatar", "logo", "icon", "emoji",
        "placeholder", "default", "/zw.", "loading", "spinner", "download",
        "github", "twitter", "qq.", "tg.", "search/",
        "/usr/themes/mirages/images/",
        "2023102511321611484.png",
        "2023102511321596540.png",
        "2023102511321783155.png",
        "2023102511321748042.png",
    ))


def merge_item_metadata(current, incoming):
    if not current:
        return dict(incoming or {})
    if not incoming:
        return dict(current)
    merged = dict(current)
    incoming_cover = incoming.get("cover_url", "")
    if needs_cover_fallback(merged.get("cover_url", "")) and incoming_cover and not needs_cover_fallback(incoming_cover):
        merged["cover_url"] = incoming_cover
    for field in ("description", "tags", "keywords", "publish_time", "play_url"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]
    if (not merged.get("play_type") or merged.get("play_type") == "unknown") and incoming.get("play_type"):
        merged["play_type"] = incoming["play_type"]
    if not merged.get("title") and incoming.get("title"):
        merged["title"] = incoming["title"]
    return merged


def backfill_fragment_items(all_items, seeds):
    for key, item in list(all_items.items()):
        if not urlparse(item.get("detail_url", "")).fragment:
            continue
        seed = seeds.get(normalize_url(item.get("detail_url", "")))
        if seed:
            all_items[key] = merge_item_metadata(item, seed)


def get_status():
    with _status_lock:
        return dict(_status)


def stop_scan():
    _stop_flag.set()
    logger.info("收到停止信号")


def scan_source_async(source_id, max_pages=DEFAULT_MAX_PAGES):
    if _status["running"]:
        return False, "扫描正在进行中"
    t = threading.Thread(target=_run_source_scan, args=(source_id, max_pages), daemon=True)
    t.start()
    return True, "扫描已启动"


def scan_all_async(max_pages=DEFAULT_MAX_PAGES):
    if _status["running"]:
        return False, "扫描正在进行中"
    t = threading.Thread(target=_run_all_scan, args=(max_pages,), daemon=True)
    t.start()
    return True, "扫描已启动"


def _update_status(**kwargs):
    with _status_lock:
        _status.update(kwargs)


def _run_source_scan(source_id, max_pages):
    source = get_source(source_id)
    if not source:
        _update_status(running=False, done=True, error=f"视频源 {source_id} 不存在")
        return
    _do_scan(source, max_pages)


def _run_all_scan(max_pages):
    sources = get_sources(enabled_only=True)
    for source in sources:
        if _stop_flag.is_set():
            break
        _do_scan(source, max_pages)


def _find_next_pages(soup, base_url, visited):
    """从页面中发现"下一页"链接。"""
    next_urls = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        for pat in NEXT_PAGE_PATTERNS:
            if pat.search(text) or pat.search(href):
                full_url = urljoin(base_url, href).split("#")[0]
                norm = normalize_url(full_url)
                if norm not in visited:
                    next_urls.append(norm)
                break
    return next_urls[:3]  # 最多 3 个下一页


def _fetch_and_extract(url, adapter_type, selectors):
    """单个页面的抓取和提取，供并发使用。"""
    try:
        html = fetch_page(url)
        items = extract_items_from_html(html, url, adapter_type, selectors)
        soup = BeautifulSoup(html, "html.parser")
        return html, items, soup
    except Exception as e:
        return None, [], None


def _do_scan(source, max_pages):
    _stop_flag.clear()
    _update_status(
        running=True, done=False, stopped=False, error="",
        source_name=source["name"],
        pages_crawled=0, videos_found=0, new_added=0, updated=0,
    )

    source_id = source["id"]
    source_name = source["name"]
    start_url = source["url"]
    adapter_type = source["adapter_type"]
    selectors = {
        "title": source.get("selector_title",""),
        "cover": source.get("selector_cover",""),
        "link": source.get("selector_link",""),
        "desc": source.get("selector_desc",""),
    }

    try:
        logger.info(f"开始全站扫描: {source_name} ({start_url})，上限 {max_pages} 页，并发 {CONCURRENCY}")
        parsed_start = urlparse(start_url)
        base_domain = parsed_start.hostname or ""

        queue = [normalize_url(start_url)]
        visited = set()
        all_items = {}
        page_seed_items = {}
        pages = 0

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            while queue:
                if _stop_flag.is_set():
                    _update_status(stopped=True)
                    logger.info("扫描已停止")
                    break
                if pages >= max_pages:
                    logger.info(f"已达到页数上限 {max_pages}")
                    break

                # 取一批待爬 URL（最多 CONCURRENCY 个）
                batch = []
                while queue and len(batch) < CONCURRENCY:
                    url = queue.pop(0)
                    norm = normalize_url(url)
                    if norm not in visited:
                        visited.add(norm)
                        batch.append((norm, url))

                if not batch:
                    break

                # 并发抓取
                futures = {}
                for norm_url, orig_url in batch:
                    if _stop_flag.is_set():
                        break
                    f = executor.submit(_fetch_and_extract, orig_url, adapter_type, selectors)
                    futures[f] = orig_url

                for future in as_completed(futures):
                    html, items, soup = future.result()
                    page_url = futures[future]
                    pages += 1

                    if items:
                        has_fragment_items = any(urlparse(item.get("detail_url", "")).fragment for item in items)
                        page_seed_item = None
                        if has_fragment_items:
                            page_seed_item = all_items.pop(normalize_item_url(page_url), None)
                        for item in items:
                            if page_seed_item:
                                if needs_cover_fallback(item.get("cover_url", "")) and page_seed_item.get("cover_url"):
                                    item["cover_url"] = page_seed_item["cover_url"]
                                if not item.get("description") and page_seed_item.get("description"):
                                    item["description"] = page_seed_item["description"]
                                if not item.get("tags") and page_seed_item.get("tags"):
                                    item["tags"] = page_seed_item["tags"]
                            durl = item.get("detail_url","")
                            if durl:
                                if not urlparse(durl).fragment:
                                    seed_key = normalize_url(durl)
                                    page_seed_items[seed_key] = merge_item_metadata(page_seed_items.get(seed_key), item)
                                nd = normalize_item_url(durl)
                                all_items[nd] = merge_item_metadata(all_items.get(nd), item)

                    # 发现新链接 + 翻页
                    if soup:
                        next_pages = _find_next_pages(soup, page_url, visited)
                        for np_url in reversed(next_pages):
                            if np_url not in visited and np_url not in queue:
                                queue.insert(0, np_url)

                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if not href or href.startswith(("#","javascript:","mailto:","tel:")):
                                continue
                            full_url = urljoin(page_url, href).split("#")[0]
                            parsed = urlparse(full_url)
                            if parsed.hostname != base_domain:
                                continue
                            if STATIC_EXT.search(parsed.path):
                                continue
                            # 跳过非内容页
                            path_lower = parsed.path.lower()
                            if path_lower.startswith("/page/"):
                                continue
                            if any(path_lower.startswith(p) for p in SKIP_PREFIXES):
                                continue
                            nf = normalize_url(full_url)
                            if nf not in visited and nf not in queue:
                                queue.append(nf)

                if pages % 20 == 0:
                    _update_status(pages_crawled=pages, videos_found=len(all_items))

        _update_status(pages_crawled=pages, videos_found=len(all_items))
        backfill_fragment_items(all_items, page_seed_items)
        logger.info(f"爬取完成: 共 {pages} 页，发现 {len(all_items)} 个视频")

        # 入库
        new_added = 0
        updated = 0
        for item in all_items.values():
            video_data = {
                "source_id": source_id, "source_name": source_name,
                "title": item.get("title",""), "cover_url": item.get("cover_url",""),
                "description": item.get("description",""), "detail_url": item.get("detail_url",""),
                "tags": item.get("tags",""), "keywords": item.get("keywords",""),
                "publish_time": item.get("publish_time",""),
                "play_url": item.get("play_url",""), "play_type": item.get("play_type","unknown"),
            }
            # 从标题自动提取标签
            if not video_data["tags"] and video_data["title"]:
                video_data["tags"] = auto_extract_tags(video_data["title"])
            # 自动提取标签
            if not video_data["tags"] and video_data["title"]:
                video_data["tags"] = auto_extract_tags(video_data["title"])
            if not video_data["play_url"] and video_data["detail_url"]:
                try:
                    play_url, play_type = extract_play_url(video_data["detail_url"], adapter_type)
                    video_data["play_url"] = play_url
                    video_data["play_type"] = play_type
                except Exception:
                    pass
            _, is_new = upsert_video(video_data)
            if is_new:
                new_added += 1
            else:
                updated += 1

        _update_status(new_added=new_added, updated=updated, running=False, done=True)
        logger.info(f"扫描完成: {source_name} — {pages} 页, {len(all_items)} 视频, 新增 {new_added}")

    except Exception as e:
        logger.error(f"扫描失败: {e}")
        _update_status(running=False, done=True, error=str(e))


def _extract_tags_from_page(html):
    """从页面中提取真实标签 — 增强版。"""
    from bs4 import BeautifulSoup
    import re as _re
    soup = BeautifulSoup(html, "html.parser")
    tags = []

    # 1. class 包含 tag/label/badge/genre/category/keyword 的元素
    for el in soup.find_all(["a", "span", "div", "li"], class_=True):
        classes = " ".join(el.get("class", []))
        if any(kw in classes.lower() for kw in ("tag", "label", "badge", "genre", "category", "keyword", "meta-tag", "video-tag")):
            text = el.get_text(strip=True)
            if text and len(text) < 30 and text not in tags:
                tags.append(text)

    # 2. rel="tag" 的链接
    for a in soup.find_all("a", rel="tag"):
        text = a.get_text(strip=True)
        if text and len(text) < 30 and text not in tags:
            tags.append(text)

    # 3. href 包含 /tag/ 或 /tags/ 的链接
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").lower()
        if "/tag/" in href or "/tags/" in href or "/keyword/" in href:
            text = a.get_text(strip=True)
            if text and len(text) < 30 and text not in tags:
                tags.append(text)

    # 4. 包含"标签/关键词/Tags/Genre/类型"文字的区域
    label_patterns = _re.compile(r"标签|关键词|Tags|Genre|类型|分类", _re.I)
    for el in soup.find_all(string=label_patterns):
        parent = el.parent
        if parent:
            # 向后查找兄弟元素
            for sibling in parent.find_next_siblings(["a", "span", "div", "li"]):
                text = sibling.get_text(strip=True)
                if text and len(text) < 30 and text not in tags:
                    tags.append(text)
                if len(tags) > 10:
                    break
            # 也检查父元素的子元素
            for child in parent.parent.find_all(["a", "span"]):
                text = child.get_text(strip=True)
                if text and len(text) < 30 and text not in tags:
                    tags.append(text)

    # 5. meta keywords
    meta = soup.find("meta", attrs={"name": "keywords"})
    if meta:
        content_text = meta.get("content", "")
        for kw in content_text.split(","):
            kw = kw.strip()
            if kw and len(kw) < 30 and kw not in tags:
                tags.append(kw)

    # 6. meta og:video:tag
    for meta in soup.find_all("meta", attrs={"property": "og:video:tag"}):
        content_text = meta.get("content", "")
        if content_text and len(content_text) < 30 and content_text not in tags:
            tags.append(content_text)

    # 7. article:tag (WordPress)
    for meta in soup.find_all("meta", attrs={"property": "article:tag"}):
        content_text = meta.get("content", "")
        if content_text and len(content_text) < 30 and content_text not in tags:
            tags.append(content_text)

    # 过滤：去掉太长的、纯数字的、常见无意义词
    stop_words = {"首页", "更多", "详情", "播放", "下载", "收藏", "分享", "评论", "查看更多", "点击播放"}
    filtered = []
    for t in tags:
        t = t.strip()
        if t and len(t) <= 20 and t not in stop_words and not t.isdigit():
            if t not in filtered:
                filtered.append(t)

    return filtered[:15]
