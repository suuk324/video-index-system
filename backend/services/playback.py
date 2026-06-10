"""Playback resolution helpers."""

from urllib.parse import urljoin, urlparse

import requests

from .. import database as db
from .extractor import HAS_PLAYWRIGHT, extract_play_url, extract_play_url_with_js


EXPIRING_URL_MARKERS = ("auth_key=", "m3u8?", ".m3u8?")
REQUEST_TIMEOUT = 30


def build_play_api_url(origin="", video_id=None, play_type="", friendly=False):
    if not video_id:
        return ""
    if friendly:
        ext = _play_extension(play_type or "m3u8")
        path = f"/api/play/{int(video_id)}.{ext}"
    else:
        path = f"/api/play?vid={int(video_id)}"
    base = (origin or "").rstrip("/")
    return f"{base}{path}" if base else path


def resolve_playback(video_id, force_refresh=False):
    video = _load_video(video_id)
    if not video:
        return None, "", "unknown"

    play_url = str(video.get("play_url") or "").strip()
    play_type = str(video.get("play_type") or "unknown").strip() or "unknown"
    detail_url = str(video.get("detail_url") or "").strip()

    should_refresh = force_refresh or not play_url or _looks_expiring(play_url)
    if should_refresh and detail_url:
        refreshed_url, refreshed_type = _extract_and_store(video, detail_url)
        if refreshed_url:
            play_url = refreshed_url
            play_type = refreshed_type or play_type

    return video, play_url, play_type


def get_play_redirect_response(video_id, force_refresh=False):
    _video, play_url, _play_type = resolve_playback(video_id, force_refresh=force_refresh)
    if not play_url:
        return 404, b"play url not found", {"content_type": "text/plain; charset=utf-8"}
    return 302, b"", {"content_type": "text/plain; charset=utf-8", "headers": {"Location": play_url}}


def get_play_stream_response(video_id, force_refresh=False):
    _video, play_url, play_type = resolve_playback(video_id, force_refresh=force_refresh)
    if not play_url:
        return 404, b"play url not found", {"content_type": "text/plain; charset=utf-8"}

    normalized_type = _normalize_play_type(play_type, play_url)
    if normalized_type == "m3u8":
        manifest = _download_manifest(play_url)
        if not manifest:
            return 502, b"play manifest fetch failed", {"content_type": "text/plain; charset=utf-8"}
        filename = f"{int(video_id)}.m3u8"
        return 200, manifest.encode("utf-8"), {
            "content_type": "application/vnd.apple.mpegurl; charset=utf-8",
            "filename": filename,
        }

    return 302, b"", {"content_type": "text/plain; charset=utf-8", "headers": {"Location": play_url}}


def _load_video(video_id):
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (int(video_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def _extract_and_store(video, detail_url):
    source = db.get_source(video.get("source_id"))
    adapter_type = source.get("adapter_type", "generic") if source else "generic"

    play_url, play_type = extract_play_url(detail_url, adapter_type)
    if not play_url and HAS_PLAYWRIGHT:
        play_url, play_type = extract_play_url_with_js(detail_url)
    if not play_url:
        return "", "unknown"

    conn = db.get_conn()
    from ..database import _now
    conn.execute(
        "UPDATE videos SET play_url=?, play_type=?, updated_at=? WHERE id=?",
        (play_url, play_type, _now(), int(video["id"])),
    )
    conn.commit()
    conn.close()
    return play_url, play_type


def _looks_expiring(url):
    lowered = str(url or "").lower()
    return any(marker in lowered for marker in EXPIRING_URL_MARKERS)


def _play_extension(play_type):
    normalized = _normalize_play_type(play_type)
    return normalized if normalized in {"m3u8", "mp4", "webm", "flv", "mkv", "avi"} else "m3u8"


def _normalize_play_type(play_type, play_url=""):
    normalized = str(play_type or "").strip().lower()
    if normalized in {"m3u8", "mp4", "webm", "flv", "mkv", "avi"}:
        return normalized

    lowered_url = str(play_url or "").lower()
    parsed_path = urlparse(lowered_url).path
    for ext in ("m3u8", "mp4", "webm", "flv", "mkv", "avi"):
        if f".{ext}" in lowered_url or parsed_path.endswith(f".{ext}"):
            return ext
    return "unknown"


def _download_manifest(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    manifest = response.content.decode("utf-8", "ignore")
    if "#EXTM3U" not in manifest:
        return ""
    return _rewrite_manifest_urls(manifest, response.url)


def _rewrite_manifest_urls(manifest, base_url):
    lines = []
    for line in manifest.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped.startswith("#EXT-X-KEY"):
            lines.append(_rewrite_key_uri(line, base_url))
            continue
        if stripped.startswith("#"):
            lines.append(line)
            continue
        lines.append(urljoin(base_url, stripped))
    return "\n".join(lines)


def _rewrite_key_uri(line, base_url):
    marker = 'URI="'
    start = line.find(marker)
    if start == -1:
        return line
    start += len(marker)
    end = line.find('"', start)
    if end == -1:
        return line
    source = line[start:end]
    target = urljoin(base_url, source)
    return f"{line[:start]}{target}{line[end:]}"
