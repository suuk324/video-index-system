"""Cover delivery helpers."""
import mimetypes
import os
import threading
import time
from collections import OrderedDict
from urllib.parse import quote, urlparse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from .. import database as db
from .extractor import extract_items_from_html, fetch_page
from .scanner import needs_cover_fallback


REQUEST_TIMEOUT = 30
CACHE_MAX_ITEMS = 256
CACHE_TTL_SECONDS = 60 * 60
ENCRYPTED_PATH_MARKERS = ("/xiao/", "/upload/upload/", "/upload_01/", "/uploads/")
ENCRYPTION_KEY = b"f5d965df75336270"
ENCRYPTION_IV = b"97b60394abc2fbe1"

_cache_lock = threading.Lock()
_cover_cache = OrderedDict()


def build_cover_api_url(origin="", video_id=None, cover_url="", friendly=False, ext="jpg"):
    base = (origin or "").rstrip("/")
    if video_id:
        if friendly:
            path = f"/api/cover/{int(video_id)}.{ext or 'jpg'}"
        else:
            path = f"/api/cover?vid={int(video_id)}"
        return f"{base}{path}" if base else path
    if cover_url:
        path = f"/api/cover?url={quote(str(cover_url), safe='')}"
        return f"{base}{path}" if base else path
    return ""


def get_cover_response(video_id=None, cover_url="", detail_url="", source_id=None):
    cover_url, detail_url, source_id = _resolve_cover_target(video_id, cover_url, detail_url, source_id)
    cache_key = (cover_url or "", detail_url or "")
    cached = _cache_get(cache_key)
    if cached:
        payload, content_type, filename = cached
        return 200, payload, {"content_type": content_type, "filename": filename}

    if not cover_url and detail_url:
        cover_url = _recover_cover_from_detail(detail_url, source_id, video_id)
    if not cover_url:
        return 404, b"cover not found", {"content_type": "text/plain; charset=utf-8"}

    image_bytes, content_type = _download_cover_bytes(cover_url, detail_url)
    if (not image_bytes or not _is_image_bytes(image_bytes)) and detail_url:
        recovered_cover = _recover_cover_from_detail(detail_url, source_id, video_id, current_cover=cover_url)
        if recovered_cover and recovered_cover != cover_url:
            cover_url = recovered_cover
            image_bytes, content_type = _download_cover_bytes(cover_url, detail_url)

    if not image_bytes or not _is_image_bytes(image_bytes):
        return 404, b"cover fetch failed", {"content_type": "text/plain; charset=utf-8"}

    filename = _filename_from_url(cover_url, content_type)
    _cache_put(cache_key, (image_bytes, content_type, filename))
    return 200, image_bytes, {"content_type": content_type, "filename": filename}


def _resolve_cover_target(video_id=None, cover_url="", detail_url="", source_id=None):
    raw_cover = str(cover_url or "").strip()
    raw_detail = str(detail_url or "").strip()
    resolved_source_id = source_id

    if video_id:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id, source_id, cover_url, detail_url FROM videos WHERE id=?",
            (int(video_id),),
        ).fetchone()
        conn.close()
        if row:
            row = dict(row)
            raw_cover = str(row.get("cover_url") or "").strip() or raw_cover
            raw_detail = str(row.get("detail_url") or "").strip() or raw_detail
            resolved_source_id = row.get("source_id")

    if needs_cover_fallback(raw_cover):
        raw_cover = ""

    return raw_cover, raw_detail, resolved_source_id


def _recover_cover_from_detail(detail_url, source_id=None, video_id=None, current_cover=""):
    detail_url = str(detail_url or "").strip()
    if not detail_url:
        return ""

    source = db.get_source(source_id) if source_id else None
    selectors = {
        "title": source.get("selector_title", "") if source else "",
        "cover": source.get("selector_cover", "") if source else "",
        "link": source.get("selector_link", "") if source else "",
        "desc": source.get("selector_desc", "") if source else "",
    }
    adapter_type = source.get("adapter_type", "generic") if source else "generic"

    try:
        html = fetch_page(detail_url)
        items = extract_items_from_html(html, detail_url, adapter_type, selectors)
    except Exception:
        return ""

    for item in items:
        candidate = str(item.get("cover_url") or "").strip()
        if candidate and not needs_cover_fallback(candidate):
            if video_id and candidate != current_cover:
                _save_recovered_cover(video_id, candidate)
            return candidate
    return ""


def _save_recovered_cover(video_id, cover_url):
    conn = db.get_conn()
    conn.execute(
        "UPDATE videos SET cover_url=?, updated_at=datetime('now', 'localtime') WHERE id=?",
        (cover_url, int(video_id)),
    )
    conn.commit()
    conn.close()


def _download_cover_bytes(url, detail_url=""):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    if detail_url:
        parsed = urlparse(detail_url)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return b"", "application/octet-stream"

    payload = response.content
    content_type = _detect_content_type(payload, url, response.headers.get("Content-Type", ""))
    if _is_image_bytes(payload):
        return payload, content_type

    if _looks_like_encrypted_cover(url, content_type):
        decrypted = _decrypt_cover_bytes(payload)
        if _is_image_bytes(decrypted):
            return decrypted, _detect_content_type(decrypted, url, content_type)

    return payload, content_type


def _looks_like_encrypted_cover(url, content_type):
    path = urlparse(str(url or "")).path.lower()
    normalized = str(content_type or "").lower()
    return any(marker in path for marker in ENCRYPTED_PATH_MARKERS) or "octet-stream" in normalized


def _decrypt_cover_bytes(payload):
    try:
        cipher = AES.new(ENCRYPTION_KEY, AES.MODE_CBC, ENCRYPTION_IV)
        return unpad(cipher.decrypt(payload), AES.block_size)
    except Exception:
        return b""


def _is_image_bytes(payload):
    if not payload:
        return False
    stripped = payload.lstrip()
    return (
        payload.startswith(b"\xff\xd8\xff")
        or payload.startswith(b"\x89PNG\r\n\x1a\n")
        or payload.startswith((b"GIF87a", b"GIF89a"))
        or payload.startswith(b"BM")
        or payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
        or stripped.startswith(b"<svg")
        or stripped.startswith(b"<?xml")
    )


def _detect_content_type(payload, url, header_value=""):
    header = str(header_value or "").split(";", 1)[0].strip().lower()
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    if payload.startswith(b"BM"):
        return "image/bmp"
    stripped = payload.lstrip()
    if stripped.startswith((b"<svg", b"<?xml")):
        return "image/svg+xml"
    if header.startswith("image/"):
        return header
    guessed = mimetypes.guess_type(urlparse(str(url or "")).path)[0]
    return guessed or "application/octet-stream"


def _filename_from_url(url, content_type):
    path = urlparse(str(url or "")).path
    filename = os.path.basename(path)
    if filename:
        return filename
    ext = mimetypes.guess_extension(content_type.split(";", 1)[0].strip().lower()) or ".img"
    return f"cover{ext}"


def _cache_get(key):
    if not any(key):
        return None
    now = time.time()
    with _cache_lock:
        cached = _cover_cache.get(key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _cover_cache.pop(key, None)
            return None
        _cover_cache.move_to_end(key)
        return payload


def _cache_put(key, payload):
    if not any(key):
        return
    with _cache_lock:
        _cover_cache[key] = (time.time() + CACHE_TTL_SECONDS, payload)
        _cover_cache.move_to_end(key)
        while len(_cover_cache) > CACHE_MAX_ITEMS:
            _cover_cache.popitem(last=False)
