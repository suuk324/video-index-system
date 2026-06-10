"""API 路由分发器"""
import ipaddress
import json
import math
import os
import socket
from . import database as db
from .services.catopen import build_catopen_bundle, build_catopen_md5
from .services.covers import build_cover_api_url, get_cover_response
from .services.playback import build_play_api_url, get_play_redirect_response, get_play_stream_response, resolve_playback


def _get_param(params, key, default=""):
    vals = params.get(key, [default])
    return vals[0] if vals else default


def dispatch(method, path, params, body):

    # ── 视频源管理 ──────────────────────────────────────────────

    if path == "/api/sources" and method == "GET":
        return 200, db.get_sources()

    if path == "/api/sources" and method == "POST":
        if not body.get("name") or not body.get("url"):
            return 400, {"detail": "name 和 url 为必填项"}
        return 201, db.create_source(body)

    # 导出视频源
    if path == "/api/sources/export" and method == "GET":
        sources = db.get_sources()
        return 200, sources

    # 导入视频源
    if path == "/api/sources/import" and method == "POST":
        if not isinstance(body, list):
            return 400, {"detail": "请求体必须是视频源数组"}
        count = 0
        for s in body:
            if s.get("name") and s.get("url"):
                db.create_source(s)
                count += 1
        return 200, {"ok": True, "imported": count}

    if path.startswith("/api/sources/") and method == "GET":
        sid = _extract_id(path, "/api/sources/")
        source = db.get_source(sid)
        if not source:
            return 404, {"detail": "视频源不存在"}
        return 200, source

    if path.startswith("/api/sources/") and method == "PUT":
        sid = _extract_id(path, "/api/sources/")
        result = db.update_source(sid, body)
        if not result:
            return 404, {"detail": "视频源不存在"}
        return 200, result

    if path.startswith("/api/sources/") and method == "DELETE":
        sid = _extract_id(path, "/api/sources/")
        if not db.delete_source(sid):
            return 404, {"detail": "视频源不存在"}
        from .scheduler import reload_scheduler
        reload_scheduler()
        return 200, {"ok": True}

    # ── 视频列表 / 搜索 ────────────────────────────────────────

    if path == "/api/videos" and method == "GET":
        keyword = _get_param(params, "keyword")
        source_id = _get_param(params, "source_id")
        tag = _get_param(params, "tag")
        category = _get_param(params, "category")
        sort = _get_param(params, "sort", "updated_at")
        favorite = _get_param(params, "favorite", "0")
        page = int(_get_param(params, "page", "1"))
        page_size = int(_get_param(params, "page_size", "30"))
        items, total = db.query_videos(
            keyword=keyword,
            source_id=int(source_id) if source_id else None,
            tag=tag, category=category,
            favorite_only=favorite == "1",
            sort=sort,
            page=page, page_size=page_size,
        )
        return 200, {
            "items": items, "total": total, "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total else 0,
        }

    if path == "/api/videos/filters" and method == "GET":
        sources = db.get_sources()
        return 200, {
            "tags": db.get_distinct_tags(),
            "categories": db.get_distinct_categories(),
            "sources": [{"id": s["id"], "name": s["name"]} for s in sources],
        }

    if path.startswith("/api/videos/") and "/favorite" in path and method == "PUT":
        vid = int(path.split("/")[3])
        result = db.toggle_favorite(vid)
        if not result:
            return 404, {"detail": "视频不存在"}
        return 200, result

    if path.startswith("/api/videos/") and "/watch" in path and method == "PUT":
        vid = int(path.split("/")[3])
        status = _get_param(params, "status", "watched")
        if status not in ("watched", "unwatched"):
            return 400, {"detail": "status 必须为 watched 或 unwatched"}
        result = db.set_watch_status(vid, status)
        if not result:
            return 404, {"detail": "视频不存在"}
        return 200, result

    # ── TVBox / M3U 订阅输出 ───────────────────────────────────

    if path in ("/api/tvbox/cms", "/api/tvbox/cms/") and method == "GET":
        return _tvbox_cms_output(params)

    if path == "/api/tvbox" and method == "GET":
        return _tvbox_output()

    if path == "/api/m3u" and method == "GET":
        return _m3u_output()

    if path == "/api/miraplay" and method == "GET":
        return _miraplay_output()

    if path == "/api/miraplay/index.js" and method == "GET":
        return _miraplay_catopen_bundle()

    if path == "/api/miraplay/index.js.md5" and method == "GET":
        return _miraplay_catopen_md5()

    if path == "/api/export/origins" and method == "GET":
        return 200, _export_origins()

    if path == "/api/cover" and method == "GET":
        video_id = _safe_int(_get_param(params, "vid"), 0)
        cover_url = _get_param(params, "url").strip()
        detail_url = _get_param(params, "detail_url").strip()
        source_id = _safe_int(_get_param(params, "source_id"), 0)
        return get_cover_response(
            video_id=video_id or None,
            cover_url=cover_url,
            detail_url=detail_url,
            source_id=source_id or None,
        )

    if path.startswith("/api/cover/") and method == "GET":
        video_id = _extract_media_id(path, "/api/cover/")
        return get_cover_response(video_id=video_id or None)

    if path == "/api/play" and method == "GET":
        video_id = _safe_int(_get_param(params, "vid"), 0)
        force_refresh = _get_param(params, "refresh", "1") != "0"
        return get_play_redirect_response(video_id=video_id, force_refresh=force_refresh)

    if path.startswith("/api/play/") and method == "GET":
        video_id = _extract_media_id(path, "/api/play/")
        force_refresh = _get_param(params, "refresh", "1") != "0"
        return get_play_stream_response(video_id=video_id, force_refresh=force_refresh)

    if path == "/api/maintenance/cover-backfill" and method == "POST":
        from .services.scanner import get_status
        if get_status().get("running"):
            return 409, {"detail": "扫描进行中，请先等待扫描完成"}
        from .services.maintenance import backfill_missing_covers
        max_pages = int(_get_param(params, "max_pages", "300"))
        return 200, backfill_missing_covers(max_pages=max_pages)

    if path == "/api/maintenance/cleanup" and method == "POST":
        from .services.scanner import get_status
        if get_status().get("running"):
            return 409, {"detail": "扫描进行中，请先等待扫描完成"}
        from .services.maintenance import cleanup_dirty_records
        return 200, cleanup_dirty_records()


    # ── 播放进度 ──────────────────────────────────────────────

    if path.startswith("/api/videos/") and "/progress" in path and method == "GET":
        vid = int(path.split("/")[3])
        result = db.get_progress(vid)
        return 200, result or {"video_id": vid, "position": 0, "duration": 0}

    if path.startswith("/api/videos/") and "/progress" in path and method == "POST":
        vid = int(path.split("/")[3])
        pos = body.get("position", 0)
        dur = body.get("duration", 0)
        db.save_progress(vid, pos, dur)
        return 200, {"ok": True}

    # ── 数据备份 ──────────────────────────────────────────────

    if path == "/api/backup" and method == "GET":
        sources = db.get_sources()
        items, _ = db.query_videos(page_size=999999)
        return 200, {"sources": sources, "videos": items, "count": {"sources": len(sources), "videos": len(items)}}

    if path == "/api/backup/import" and method == "POST":
        imported_s = 0
        imported_v = 0
        if "sources" in body:
            for s in body["sources"]:
                if s.get("name") and s.get("url"):
                    db.create_source(s)
                    imported_s += 1
        if "videos" in body:
            for v in body["videos"]:
                if v.get("detail_url") and v.get("source_id"):
                    db.upsert_video(v)
                    imported_v += 1
        return 200, {"ok": True, "imported_sources": imported_s, "imported_videos": imported_v}

    # ── 扫描 ───────────────────────────────────────────────────

    if path == "/api/scan/status" and method == "GET":
        from .services.scanner import get_status
        return 200, get_status()

    if path == "/api/scan/stop" and method == "POST":
        from .services.scanner import stop_scan
        stop_scan()
        return 200, {"ok": True, "message": "停止信号已发送"}

    if path == "/api/scan" and method == "POST":
        from .services.scanner import scan_all_async
        max_pages = int(_get_param(params, "max_pages", "5000"))
        ok, msg = scan_all_async(max_pages)
        return (200 if ok else 409), {"ok": ok, "message": msg}

    if path.startswith("/api/scan/") and method == "POST":
        sid = _extract_id(path, "/api/scan/")
        source = db.get_source(sid)
        if not source:
            return 404, {"detail": "视频源不存在"}
        max_pages = int(_get_param(params, "max_pages", "5000"))
        from .services.scanner import scan_source_async
        ok, msg = scan_source_async(sid, max_pages)
        return (200 if ok else 409), {"ok": ok, "message": msg}



    # ── 实时提取播放链接 ──────────────────────────────────────

    if path.startswith("/api/videos/") and "/play-url" in path and method == "POST":
        vid = int(path.split("/")[3])
        video, play_url, play_type = resolve_playback(vid, force_refresh=True)
        if not video:
            return 404, {"detail": "视频不存在"}
        detail_url = video.get("detail_url", "")
        if not detail_url:
            return 400, {"detail": "无详情页链接"}

        if play_url:
            return 200, {"play_url": play_url, "play_type": play_type}

        return 200, {"play_url": "", "play_type": "unknown", "message": "未找到视频链接"}


    # ── 自定义适配器 ──────────────────────────────────────────

    if path == "/api/adapters" and method == "GET":
        return 200, db.get_custom_adapters()

    if path == "/api/adapters" and method == "POST":
        if not body.get("name") or not body.get("url_pattern"):
            return 400, {"detail": "name 和 url_pattern 为必填项"}
        return 201, db.create_custom_adapter(body)

    if path.startswith("/api/adapters/") and method == "GET":
        aid = _extract_id(path, "/api/adapters/")
        adapter = db.get_custom_adapter(aid)
        if not adapter:
            return 404, {"detail": "适配器不存在"}
        return 200, adapter

    if path.startswith("/api/adapters/") and method == "PUT":
        aid = _extract_id(path, "/api/adapters/")
        result = db.update_custom_adapter(aid, body)
        if not result:
            return 404, {"detail": "适配器不存在"}
        return 200, result

    if path.startswith("/api/adapters/") and method == "DELETE":
        aid = _extract_id(path, "/api/adapters/")
        if not db.delete_custom_adapter(aid):
            return 404, {"detail": "适配器不存在"}
        return 200, {"ok": True}

    # ── 调试接口 ──────────────────────────────────────────────

    if path == "/api/debug/fetch" and method == "GET":
        url = _get_param(params, "url")
        if not url:
            return 400, {"detail": "需要 url 参数"}
        try:
            from .services.extractor import fetch_page
            html = fetch_page(url)
            return 200, {"url": url, "html_length": len(html), "html_preview": html[:3000]}
        except Exception as e:
            return 500, {"detail": str(e)}

    if path == "/api/debug/extract" and method == "GET":
        url = _get_param(params, "url")
        if not url:
            return 400, {"detail": "需要 url 参数"}
        try:
            from .services.extractor import fetch_page, extract_items_from_html
            from .adapters.generic import GenericAdapter
            html = fetch_page(url)
            adapter = GenericAdapter()
            items = adapter.extract_items(html, url, {})
            play_url, play_type = adapter.extract_play_url(html, url)
            return 200, {
                "url": url,
                "html_length": len(html),
                "items_found": len(items),
                "items": items[:10],
                "play_url": play_url,
                "play_type": play_type,
            }
        except Exception as e:
            return 500, {"detail": str(e)}

    return 404, {"detail": f"未找到路由: {method} {path}"}


def _tvbox_output():
    """TVBox JSON 格式输出。"""
    items, _ = db.query_videos(page_size=99999)
    source_labels = _source_label_map()
    categories = {}
    for v in items:
        cat = source_labels.get(v.get("source_id")) or v.get("source_name") or "未分类"
        if cat not in categories:
            categories[cat] = []
        play_url = v.get("play_url") or v.get("detail_url") or ""
        categories[cat].append({
            "vod_name": v.get("title", ""),
            "vod_pic": v.get("cover_url", ""),
            "vod_remarks": v.get("description", "")[:50],
            "vod_play_url": play_url,
        })

    result = []
    for cat_name, vods in categories.items():
        result.append({
            "type_id": cat_name,
            "type_name": cat_name,
            "vod_list": vods,
        })

    payload = json.dumps({
        "code": 1,
        "page": 1,
        "pagecount": 1,
        "limit": len(items),
        "total": len(items),
        "list": result
    }, ensure_ascii=False)
    return _raw_response(payload, "application/json; charset=utf-8", "tvbox.json")


def _m3u_output():
    """M3U 格式输出。"""
    items, _ = db.query_videos(page_size=99999)
    source_labels = _source_label_map()
    export = _export_origins()
    origin = export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"
    lines = ["#EXTM3U"]
    for v in items:
        title = v.get("title", "").replace(",", " ")
        url = build_play_api_url(
            origin=origin,
            video_id=v.get("id"),
            play_type=v.get("play_type", ""),
            friendly=True,
        ) if (v.get("play_url") or v.get("detail_url")) else ""
        cover = build_cover_api_url(
            origin=origin,
            video_id=v.get("id"),
            cover_url=v.get("cover_url", ""),
            friendly=True,
        )
        group = source_labels.get(v.get("source_id")) or v.get("source_name", "")
        if url:
            ext = f'#EXTINF:-1 tvg-logo="{cover}" group-title="{group}",{title}'
            lines.append(ext)
            lines.append(url)

    content = "\n".join(lines)
    return _raw_response(content, "application/x-mpegURL; charset=utf-8", "playlist.m3u")


def _miraplay_output():
    """Miraplay JSON 格式输出。"""
    items, _ = db.query_videos(page_size=99999)
    source_labels = _source_label_map()
    export = _export_origins()
    origin = export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"
    categories = {}
    for v in items:
        cat = source_labels.get(v.get("source_id")) or v.get("source_name") or "未分类"
        if cat not in categories:
            categories[cat] = {"name": cat, "list": []}
        play_url = build_play_api_url(
            origin=origin,
            video_id=v.get("id"),
            play_type=v.get("play_type", ""),
            friendly=True,
        ) if (v.get("play_url") or v.get("detail_url")) else ""
        categories[cat]["list"].append({
            "name": v.get("title", ""),
            "pic": build_cover_api_url(
                origin=origin,
                video_id=v.get("id"),
                cover_url=v.get("cover_url", ""),
                friendly=True,
            ),
            "url": play_url,
            "desc": v.get("description", "")[:100],
        })
    result = {
        "code": 1,
        "msg": "success",
        "data": {
            "class": [{"type_id": k, "type_name": k} for k in categories.keys()],
            "list": list(categories.values()),
        }
    }
    payload = json.dumps(result, ensure_ascii=False)
    return _raw_response(payload, "application/json; charset=utf-8", "miraplay.json")


def _miraplay_catopen_bundle():
    export = _export_origins()
    origin = export.get("public_origin") or export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"
    payload = build_catopen_bundle(origin)
    return _raw_response(payload, "text/javascript; charset=utf-8", "index.js")


def _miraplay_catopen_md5():
    export = _export_origins()
    origin = export.get("public_origin") or export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"
    bundle = build_catopen_bundle(origin)
    payload = build_catopen_md5(bundle)
    return _raw_response(payload, "text/plain; charset=utf-8", "index.js.md5")


def _extract_id(path, prefix):
    rest = path[len(prefix):]
    return int(rest.split("/")[0])


def _extract_media_id(path, prefix):
    rest = path[len(prefix):]
    head = rest.split("/", 1)[0]
    candidate = head.split(".", 1)[0]
    return _safe_int(candidate, 0)


def _raw_response(content, content_type, filename=""):
    return 200, content, {"content_type": content_type, "filename": filename}


def _source_label_map():
    labels = {}
    for source in db.get_sources():
        name = str(source.get("name", "")).strip()
        url = str(source.get("url", "")).strip()
        label = name
        if not label or label.isdigit():
            try:
                from urllib.parse import urlparse
                label = (urlparse(url).hostname or "").replace("www.", "")
            except Exception:
                label = name
        labels[source.get("id")] = label or name or "未分类"
    return labels


def _is_private_ipv4(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 4 and addr.is_private and not addr.is_loopback and not addr.is_link_local


def _collect_lan_ipv4():
    candidates = []
    seen = set()

    def add(ip):
        if not _is_private_ipv4(ip) or ip in seen:
            return
        seen.add(ip)
        candidates.append(ip)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            add(info[4][0])
    except OSError:
        pass

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            add(ip)
    except OSError:
        pass

    return candidates


def _load_public_origin():
    public_origin = str(os.environ.get("PUBLIC_ORIGIN", "")).strip()
    if public_origin:
        return public_origin.rstrip("/")
    project_root = os.path.dirname(os.path.dirname(__file__))
    origin_file = os.path.join(project_root, "public_origin.txt")
    try:
        with open(origin_file, "r", encoding="utf-8") as fh:
            return fh.read().strip().rstrip("/")
    except OSError:
        return ""


def _export_origins():
    port = int(os.environ.get("PORT", "8000"))
    lan_ips = _collect_lan_ipv4()
    public_origin = _load_public_origin()
    origins = []
    if public_origin:
        origins.append(public_origin)
    origins.extend(f"http://{ip}:{port}" for ip in lan_ips)
    return {
        "port": port,
        "lan_ips": lan_ips,
        "origins": origins,
        "public_origin": public_origin,
        "preferred_origin": origins[0] if origins else "",
    }


def _safe_int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _tvbox_match_keyword(video, keyword):
    haystacks = [
        str(video.get("title", "")),
        str(video.get("description", "")),
        str(video.get("tags", "")),
        str(video.get("keywords", "")),
    ]
    needle = str(keyword or "").lower()
    return any(needle in text.lower() for text in haystacks if text)


def _tvbox_remarks(video):
    if video.get("play_url"):
        return str(video.get("play_type") or "").upper() or "直连"
    if video.get("detail_url"):
        return "本地解析"
    return ""


def _tvbox_classes(items, source_labels):
    seen = set()
    classes = [{"type_id": "__all__", "type_name": "全部"}]
    tag_counts = {}
    for video in items:
        label = source_labels.get(video.get("source_id")) or video.get("source_name") or "未分类"
        if label and label not in seen:
            seen.add(label)
            classes.append({"type_id": label, "type_name": label})
        for tag in _split_tags(video.get("tags", "")):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    for tag, _count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:12]:
        classes.append({"type_id": f"tag:{tag}", "type_name": tag})
    return classes


def _split_tags(raw_tags):
    tags = []
    seen = set()
    for part in str(raw_tags or "").split(","):
        tag = part.strip()
        lowered = tag.lower()
        if tag and lowered not in seen:
            seen.add(lowered)
            tags.append(tag)
    return tags


def _tvbox_output():
    """TVBox 配置仓输出。"""
    export = _export_origins()
    origin = export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"
    cms_api = f"{origin}/api/tvbox/cms"
    payload = json.dumps({
        "sites": [
            {
                "key": "local-video-aggregator",
                "name": "本地视频聚合",
                "type": 1,
                "api": cms_api,
                "searchable": 1,
                "quickSearch": 1,
                "filterable": 1,
            }
        ],
        "parses": [],
        "lives": [],
    }, ensure_ascii=False)
    return _raw_response(payload, "application/json; charset=utf-8", "tvbox.json")


def _tvbox_cms_output(params):
    """TVBox 兼容的 CMS 接口。"""
    source_labels = _source_label_map()
    ids = _get_param(params, "ids").strip()

    if ids:
        return _tvbox_cms_detail(ids, source_labels)
    return _tvbox_cms_list(params, source_labels)


def _tvbox_cms_list(params, source_labels):
    page = max(1, _safe_int(_get_param(params, "pg", "1"), 1))
    page_size = max(1, min(_safe_int(_get_param(params, "limit", "30"), 30), 100))
    keyword = _get_param(params, "wd").strip().lower()
    type_id = _get_param(params, "t").strip()
    export = _export_origins()
    origin = export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"

    items, _ = db.query_videos(page_size=99999)
    classes = _tvbox_classes(items, source_labels)
    filtered = []

    for video in items:
        label = source_labels.get(video.get("source_id")) or video.get("source_name") or "未分类"
        if not (video.get("title") or "").strip():
            continue
        if type_id and type_id != "__all__":
            if type_id.startswith("tag:"):
                if type_id[4:] not in _split_tags(video.get("tags", "")):
                    continue
            elif label != type_id:
                continue
        if keyword and not _tvbox_match_keyword(video, keyword):
            continue
        filtered.append({
            "vod_id": str(video.get("id", "")),
            "vod_name": video.get("title", ""),
            "vod_pic": build_cover_api_url(
                origin=origin,
                video_id=video.get("id"),
                cover_url=video.get("cover_url", ""),
                friendly=True,
            ),
            "vod_remarks": _tvbox_remarks(video),
            "type_name": label,
        })

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]
    pagecount = math.ceil(total / page_size) if total else 0

    payload = json.dumps({
        "code": 1,
        "msg": "success",
        "page": page,
        "pagecount": pagecount,
        "limit": page_size,
        "total": total,
        "class": classes,
        "list": page_items,
    }, ensure_ascii=False)
    return _raw_response(payload, "application/json; charset=utf-8")


def _tvbox_cms_detail(ids, source_labels):
    id_list = [item for item in {item.strip() for item in ids.split(",")} if item.isdigit()]
    if not id_list:
        payload = json.dumps({"code": 1, "msg": "success", "list": []}, ensure_ascii=False)
        return _raw_response(payload, "application/json; charset=utf-8")
    export = _export_origins()
    origin = export.get("preferred_origin") or f"http://127.0.0.1:{export['port']}"

    placeholders = ",".join("?" for _ in id_list)
    conn = db.get_conn()
    rows = conn.execute(
        f"SELECT * FROM videos WHERE id IN ({placeholders}) ORDER BY updated_at DESC, id DESC",
        [int(item) for item in id_list],
    ).fetchall()
    conn.close()

    details = []
    for row in rows:
        video = dict(row)
        label = source_labels.get(video.get("source_id")) or video.get("source_name") or "未分类"
        play_url = build_play_api_url(
            origin=origin,
            video_id=video.get("id"),
            play_type=video.get("play_type", ""),
            friendly=True,
        ) if (video.get("play_url") or video.get("detail_url")) else ""
        details.append({
            "vod_id": str(video.get("id", "")),
            "vod_name": video.get("title", ""),
            "vod_pic": build_cover_api_url(
                origin=origin,
                video_id=video.get("id"),
                cover_url=video.get("cover_url", ""),
                friendly=True,
            ),
            "type_name": label,
            "vod_remarks": _tvbox_remarks(video),
            "vod_content": video.get("description", ""),
            "vod_play_from": "本地解析" if play_url else "",
            "vod_play_url": f"播放${play_url}" if play_url else "",
        })

    payload = json.dumps({
        "code": 1,
        "msg": "success",
        "page": 1,
        "pagecount": 1,
        "limit": len(details),
        "total": len(details),
        "list": details,
    }, ensure_ascii=False)
    return _raw_response(payload, "application/json; charset=utf-8")
