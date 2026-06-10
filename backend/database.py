"""数据库初始化与 CRUD 操作"""
import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.db")
)

ORDER_MAP = {
    "updated_at": "updated_at DESC, id DESC",
    "created_at": "created_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC, id DESC",
    "source_name": "source_name COLLATE NOCASE ASC, title COLLATE NOCASE ASC, id DESC",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS video_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT DEFAULT '',
        url TEXT NOT NULL,
        refresh_interval INTEGER DEFAULT 3600,
        enabled INTEGER DEFAULT 1,
        adapter_type TEXT DEFAULT 'generic',
        selector_title TEXT DEFAULT '',
        selector_cover TEXT DEFAULT '',
        selector_link TEXT DEFAULT '',
        selector_desc TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        cover_url TEXT DEFAULT '',
        description TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        keywords TEXT DEFAULT '',
        publish_time TEXT DEFAULT '',
        detail_url TEXT NOT NULL DEFAULT '',
        play_url TEXT DEFAULT '',
        play_type TEXT DEFAULT 'unknown',
        source_name TEXT DEFAULT '',
        is_favorite INTEGER DEFAULT 0,
        watch_status TEXT DEFAULT 'unwatched',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (source_id) REFERENCES video_sources(id) ON DELETE CASCADE,
        UNIQUE(detail_url, source_id)
    );

    CREATE INDEX IF NOT EXISTS idx_videos_source_id ON videos(source_id);
    CREATE INDEX IF NOT EXISTS idx_videos_title ON videos(title);
    CREATE INDEX IF NOT EXISTS idx_videos_is_favorite ON videos(is_favorite);
    CREATE INDEX IF NOT EXISTS idx_videos_updated_at ON videos(updated_at);
    CREATE INDEX IF NOT EXISTS idx_videos_source_name ON videos(source_name);

    CREATE TABLE IF NOT EXISTS custom_adapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        url_pattern TEXT NOT NULL,
        list_selector TEXT DEFAULT '',
        title_selector TEXT DEFAULT '',
        cover_selector TEXT DEFAULT '',
        link_selector TEXT DEFAULT '',
        desc_selector TEXT DEFAULT '',
        detail_title_selector TEXT DEFAULT '',
        detail_cover_selector TEXT DEFAULT '',
        detail_desc_selector TEXT DEFAULT '',
        play_url_pattern TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS playback_progress (
        video_id INTEGER PRIMARY KEY,
        position REAL DEFAULT 0,
        duration REAL DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_source(data):
    conn = get_conn()
    now = _now()
    cur = conn.execute("""
        INSERT INTO video_sources (name, category, url, refresh_interval, enabled, adapter_type,
            selector_title, selector_cover, selector_link, selector_desc, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data["name"], data.get("category",""), data["url"],
          data.get("refresh_interval",3600), data.get("enabled",1),
          data.get("adapter_type","generic"),
          data.get("selector_title",""), data.get("selector_cover",""),
          data.get("selector_link",""), data.get("selector_desc",""),
          now, now))
    conn.commit()
    row = conn.execute("SELECT * FROM video_sources WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_sources(enabled_only=False):
    conn = get_conn()
    if enabled_only:
        rows = conn.execute("SELECT * FROM video_sources WHERE enabled=1 ORDER BY id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM video_sources ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_source(source_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM video_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_source(source_id, data):
    conn = get_conn()
    fields = []
    values = []
    for key in ("name","category","url","refresh_interval","enabled","adapter_type",
                "selector_title","selector_cover","selector_link","selector_desc"):
        if key in data:
            fields.append(f"{key}=?")
            values.append(data[key])
    if not fields:
        conn.close()
        return get_source(source_id)
    fields.append("updated_at=?")
    values.append(_now())
    values.append(source_id)
    conn.execute(f"UPDATE video_sources SET {','.join(fields)} WHERE id=?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM video_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_source(source_id):
    conn = get_conn()
    conn.execute("DELETE FROM videos WHERE source_id=?", (source_id,))
    cur = conn.execute("DELETE FROM video_sources WHERE id=?", (source_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def upsert_video(data):
    conn = get_conn()
    now = _now()
    existing = conn.execute("SELECT id FROM videos WHERE detail_url=? AND source_id=?",
                            (data["detail_url"], data["source_id"])).fetchone()
    if existing:
        conn.execute("""
            UPDATE videos SET title=?, cover_url=?, description=?, tags=?, keywords=?,
                publish_time=?, play_url=?, play_type=?, source_name=?, updated_at=?
            WHERE id=?""", (
            data.get("title",""), data.get("cover_url",""),
            data.get("description",""), data.get("tags",""),
            data.get("keywords",""), data.get("publish_time",""),
            data.get("play_url",""), data.get("play_type","unknown"),
            data.get("source_name",""), now, existing["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM videos WHERE id=?", (existing["id"],)).fetchone()
        conn.close()
        return dict(row), False
    else:
        cur = conn.execute("""
            INSERT INTO videos (source_id, title, cover_url, description, tags, keywords,
                publish_time, detail_url, play_url, play_type, source_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            data["source_id"], data.get("title",""), data.get("cover_url",""),
            data.get("description",""), data.get("tags",""),
            data.get("keywords",""), data.get("publish_time",""),
            data["detail_url"], data.get("play_url",""),
            data.get("play_type","unknown"), data.get("source_name",""),
            now, now))
        conn.commit()
        row = conn.execute("SELECT * FROM videos WHERE id=?", (cur.lastrowid,)).fetchone()
        conn.close()
        return dict(row), True


def query_videos(keyword="", source_id=None, tag="", category="", favorite_only=False, sort="updated_at", page=1, page_size=30):
    conditions = []
    params = []
    if keyword:
        conditions.append("(title LIKE ? OR description LIKE ? OR tags LIKE ? OR keywords LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw, kw])
    if source_id is not None:
        conditions.append("source_id=?")
        params.append(source_id)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    if category:
        conditions.append("source_name IN (SELECT name FROM video_sources WHERE category=?)")
        params.append(category)
    if favorite_only:
        conditions.append("is_favorite=1")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    order_clause = ORDER_MAP.get((sort or "updated_at").strip().lower(), ORDER_MAP["updated_at"])
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM videos {where}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(f"SELECT * FROM videos {where} ORDER BY {order_clause} LIMIT ? OFFSET ?",
                        params + [page_size, offset]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def toggle_favorite(video_id):
    conn = get_conn()
    row = conn.execute("SELECT is_favorite FROM videos WHERE id=?", (video_id,)).fetchone()
    if not row:
        conn.close()
        return None
    new_val = 0 if row["is_favorite"] else 1
    conn.execute("UPDATE videos SET is_favorite=?, updated_at=? WHERE id=?", (new_val, _now(), video_id))
    conn.commit()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    conn.close()
    return dict(row)


def set_watch_status(video_id, status):
    conn = get_conn()
    conn.execute("UPDATE videos SET watch_status=?, updated_at=? WHERE id=?", (status, _now(), video_id))
    conn.commit()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_distinct_tags():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT tags FROM videos WHERE tags!=''").fetchall()
    conn.close()
    tags = set()
    for r in rows:
        for t in r["tags"].split(","):
            t = t.strip()
            if t: tags.add(t)
    return sorted(tags)


def get_distinct_categories():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT category FROM video_sources WHERE category!=''").fetchall()
    conn.close()
    return sorted([r["category"] for r in rows])


def save_progress(video_id, position, duration=0):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO playback_progress (video_id, position, duration, updated_at)
        VALUES (?, ?, ?, ?)
    """, (video_id, position, duration, _now()))
    conn.commit()
    conn.close()


def get_progress(video_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM playback_progress WHERE video_id=?", (video_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_progress():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM playback_progress").fetchall()
    conn.close()
    return {r["video_id"]: dict(r) for r in rows}


def auto_extract_tags(title):
    """从标题中自动提取关键词作为标签。"""
    if not title:
        return ""
    import re
    # 常见标签关键词
    tag_keywords = {
        "动作": ["动作","打斗","格斗","武术","功夫"],
        "喜剧": ["喜剧","搞笑","幽默","欢乐"],
        "爱情": ["爱情","恋爱","浪漫","情"],
        "科幻": ["科幻","太空","未来","机器人","外星"],
        "恐怖": ["恐怖","惊悚","鬼","僵尸","血腥"],
        "悬疑": ["悬疑","推理","侦探","犯罪","谜"],
        "动画": ["动画","动漫","卡通"],
        "纪录片": ["纪录","纪实","自然","历史"],
        "剧情": ["剧情","故事","人生"],
        "战争": ["战争","军事","战场"],
        "奇幻": ["奇幻","魔幻","神话","仙侠"],
    }
    found = []
    title_lower = title.lower()
    for tag, keywords in tag_keywords.items():
        for kw in keywords:
            if kw in title:
                found.append(tag)
                break
    # 提取年份
    year_match = re.search(r'(20\d{2}|19\d{2})', title)
    if year_match:
        found.append(year_match.group(1))
    return ",".join(found[:5])


def create_custom_adapter(data):
    conn = get_conn()
    now = _now()
    cur = conn.execute("""
        INSERT INTO custom_adapters (name, description, url_pattern,
            list_selector, title_selector, cover_selector, link_selector, desc_selector,
            detail_title_selector, detail_cover_selector, detail_desc_selector,
            play_url_pattern, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["name"], data.get("description",""), data["url_pattern"],
        data.get("list_selector",""), data.get("title_selector",""),
        data.get("cover_selector",""), data.get("link_selector",""),
        data.get("desc_selector",""), data.get("detail_title_selector",""),
        data.get("detail_cover_selector",""), data.get("detail_desc_selector",""),
        data.get("play_url_pattern",""), data.get("enabled",1),
        now, now
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM custom_adapters WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_custom_adapters():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM custom_adapters ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_custom_adapter(adapter_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM custom_adapters WHERE id=?", (adapter_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_custom_adapter(adapter_id, data):
    conn = get_conn()
    fields = []
    values = []
    for key in ("name","description","url_pattern","list_selector","title_selector",
                "cover_selector","link_selector","desc_selector","detail_title_selector",
                "detail_cover_selector","detail_desc_selector","play_url_pattern","enabled"):
        if key in data:
            fields.append(f"{key}=?")
            values.append(data[key])
    if not fields:
        conn.close()
        return get_custom_adapter(adapter_id)
    fields.append("updated_at=?")
    values.append(_now())
    values.append(adapter_id)
    conn.execute(f"UPDATE custom_adapters SET {','.join(fields)} WHERE id=?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM custom_adapters WHERE id=?", (adapter_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_custom_adapter(adapter_id):
    conn = get_conn()
    cur = conn.execute("DELETE FROM custom_adapters WHERE id=?", (adapter_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def find_custom_adapter_for_url(url):
    """根据 URL 匹配自定义适配器。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM custom_adapters WHERE enabled=1").fetchall()
    conn.close()
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    for row in rows:
        pattern = row["url_pattern"]
        if pattern and (pattern in url or pattern in domain):
            return dict(row)
    return None
