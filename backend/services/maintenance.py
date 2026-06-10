"""后台维护服务：封面回填与脏数据清理。"""
import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse

from .. import database as db
from .extractor import fetch_page, extract_items_from_html
from .scanner import SKIP_PREFIXES, needs_cover_fallback


INVALID_DETAIL_PATHS = {
    "/",
    "/github.html",
    "/qun.html",
    "/telegram.html",
    "/twitter.html",
    "/app.html",
}

INVALID_DETAIL_PREFIXES = (
    "/ai/",
    "/advertiser/",
    "/terms",
)


def _source_selectors(source):
    return {
        "title": source.get("selector_title", ""),
        "cover": source.get("selector_cover", ""),
        "link": source.get("selector_link", ""),
        "desc": source.get("selector_desc", ""),
    }


def _path_key(url):
    parsed = urlparse(url or "")
    path = (parsed.path or "/").rstrip("/") or "/"
    return path


def _classify_dirty_detail(detail_url):
    parsed = urlparse(detail_url or "")
    path = (parsed.path or "/").lower().rstrip("/") or "/"
    if path in INVALID_DETAIL_PATHS:
        return "invalid_page"
    if any(path.startswith(prefix.rstrip("/")) for prefix in SKIP_PREFIXES):
        return "non_content_path"
    if any(path.startswith(prefix.rstrip("/")) for prefix in INVALID_DETAIL_PREFIXES):
        return "tooling_or_terms"
    if re.search(r"^/archives/page/\d+$", path):
        return "archive_pager"
    return ""


def cleanup_dirty_records():
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT id, detail_url, title, play_url
        FROM videos
        ORDER BY id
    """).fetchall()

    deleted = []
    reason_counter = defaultdict(int)
    for row in rows:
        reason = _classify_dirty_detail(row["detail_url"])
        if not reason:
            continue
        conn.execute("DELETE FROM videos WHERE id=?", (row["id"],))
        reason_counter[reason] += 1
        if len(deleted) < 20:
            deleted.append({
                "id": row["id"],
                "detail_url": row["detail_url"],
                "title": row["title"],
                "reason": reason,
            })

    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    conn.close()

    return {
        "ok": True,
        "action": "cleanup_dirty",
        "deleted_rows": sum(reason_counter.values()),
        "remaining_rows": remaining,
        "reasons": dict(reason_counter),
        "examples": deleted,
    }


def backfill_missing_covers(max_pages=300):
    sources = db.get_sources()
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT id, source_id, detail_url, cover_url
        FROM videos
        ORDER BY id
    """).fetchall()

    targets_by_source = defaultdict(lambda: defaultdict(list))
    detail_targets = defaultdict(list)
    for row in rows:
        if not needs_cover_fallback(row["cover_url"]):
            continue
        targets_by_source[row["source_id"]][_path_key(row["detail_url"])].append(row["id"])
        detail_targets[row["source_id"]].append({
            "id": row["id"],
            "detail_url": row["detail_url"],
        })

    total_targets = sum(len(items) for items in detail_targets.values())
    updated_rows = 0
    source_reports = []

    for source in sources:
        target_map = targets_by_source.get(source["id"])
        if not target_map:
            continue

        found_cover_by_path = {}
        found_cover_by_video = {}
        empty_streak = 0
        pages_tried = 0
        detail_pages_tried = 0

        for page in range(1, max_pages + 1):
            page_url = source["url"] if page == 1 else urljoin(source["url"], f"/page/{page}/")
            pages_tried = page
            try:
                html = fetch_page(page_url)
                items = extract_items_from_html(
                    html,
                    page_url,
                    source.get("adapter_type", "generic"),
                    _source_selectors(source),
                )
            except Exception:
                empty_streak += 1
                if empty_streak >= 5:
                    break
                continue

            if not items:
                empty_streak += 1
                if empty_streak >= 5:
                    break
                continue

            empty_streak = 0
            for item in items:
                cover_url = (item.get("cover_url") or "").strip()
                if not cover_url or needs_cover_fallback(cover_url):
                    continue
                target_key = _path_key(item.get("detail_url", ""))
                if target_key in target_map and target_key not in found_cover_by_path:
                    found_cover_by_path[target_key] = cover_url

            if len(found_cover_by_path) == len(target_map):
                break

        remaining_details = [
            target for target in detail_targets.get(source["id"], [])
            if target["id"] not in found_cover_by_video
            and _path_key(target["detail_url"]) not in found_cover_by_path
        ]
        for target in remaining_details:
            detail_pages_tried += 1
            try:
                html = fetch_page(target["detail_url"])
                detail_items = extract_items_from_html(
                    html,
                    target["detail_url"],
                    source.get("adapter_type", "generic"),
                    _source_selectors(source),
                )
            except Exception:
                continue

            cover_url = ""
            for item in detail_items:
                candidate = (item.get("cover_url") or "").strip()
                if candidate and not needs_cover_fallback(candidate):
                    cover_url = candidate
                    break
            if cover_url:
                found_cover_by_video[target["id"]] = cover_url

        matched_rows = 0
        for target_key, cover_url in found_cover_by_path.items():
            for video_id in target_map[target_key]:
                conn.execute(
                    "UPDATE videos SET cover_url=?, updated_at=datetime('now', 'localtime') WHERE id=?",
                    (cover_url, video_id),
                )
                matched_rows += 1
        for video_id, cover_url in found_cover_by_video.items():
            conn.execute(
                "UPDATE videos SET cover_url=?, updated_at=datetime('now', 'localtime') WHERE id=?",
                (cover_url, video_id),
            )
            matched_rows += 1

        updated_rows += matched_rows
        target_rows = len(detail_targets.get(source["id"], []))
        source_reports.append({
            "source_id": source["id"],
            "source_name": source.get("name", ""),
            "pages_tried": pages_tried,
            "detail_pages_tried": detail_pages_tried,
            "target_rows": target_rows,
            "updated_rows": matched_rows,
            "remaining_rows": max(0, target_rows - matched_rows),
        })

    conn.commit()
    remaining_rows = 0
    for row in conn.execute("SELECT cover_url FROM videos").fetchall():
        if needs_cover_fallback(row["cover_url"]):
            remaining_rows += 1
    conn.close()

    return {
        "ok": True,
        "action": "cover_backfill",
        "source_count": len(source_reports),
        "target_rows": total_targets,
        "updated_rows": updated_rows,
        "remaining_rows": remaining_rows,
        "max_pages": max_pages,
        "sources": source_reports,
    }
