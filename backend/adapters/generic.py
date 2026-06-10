"""通用网页适配器 — 最终版"""
import re
import json
from html import unescape
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from . import BaseAdapter, AdapterRegistry


def _abs_url(url, base):
    if not url: return ""
    if url.startswith(("http://", "https://", "//")): return url
    return urljoin(base, url)


def _detect_play_type(url):
    u = url.lower().split("?")[0]
    if u.endswith(".m3u8"): return "m3u8"
    if u.endswith(".mp4"): return "mp4"
    if u.endswith(".webm"): return "webm"
    if u.endswith(".flv"): return "flv"
    return "unknown"


def _get_img_src(img):
    if not img: return ""
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-echo", "data-url", "data-image", "data-thumb"):
        val = img.get(attr, "")
        if val and not val.startswith("data:"):
            return val
    srcset = img.get("srcset") or img.get("data-srcset") or ""
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0].strip()
        if first and not first.startswith("data:"):
            return first
    return ""


PLACEHOLDER_IMAGE_PATTERNS = (
    "social-default", "banner", "avatar", "logo", "icon", "emoji",
    "placeholder", "default", "/zw.", "loading", "spinner", "download",
    "github", "twitter", "qq.", "tg.", "search/", "chigua.png",
    "/usr/themes/mirages/images/",
    "2023102511321611484.png",
    "2023102511321596540.png",
    "2023102511321783155.png",
    "2023102511321748042.png",
)


DETAIL_PATTERNS = [
    "/archives/", "/post/", "/article/", "/v/", "/video/",
    "/detail/", "/p/", "/vod/play/", "/movie/", "/play/",
]

SKIP_PREFIXES = [
    "/author/", "/category/", "/tag/", "/tags/", "/page/",
    "/wp-admin/", "/wp-login", "/wp-content/", "/wp-includes/",
    "/feed/", "/comment", "/search/", "/user/", "/profile/",
    "/login", "/register/", "/about", "/contact",
]


def _score_as_detail(url):
    path = urlparse(url).path.lower()
    if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return 0
    if re.search(r'(^|/)page/\d+/?$', path):
        return 0
    score = 0
    for pat in DETAIL_PATTERNS:
        if pat in path: score += 5
    parts = [p for p in path.split("/") if p]
    if any(re.search(r"\d{2,}", p) for p in parts): score += 2
    if len(parts) >= 2: score += 1
    return score


def _base_page_url(url):
    return url.split("#", 1)[0]


def _normalize_player_fragment(raw_fragment):
    fragment = (raw_fragment or "").strip()
    if not fragment:
        return ""
    if fragment.startswith("video-"):
        return fragment[6:]
    return fragment


def _build_player_detail_url(base_url, player_id, index):
    fragment = f"video-{player_id or index}"
    return f"{_base_page_url(base_url)}#{fragment}"


def _load_player_config(raw_config):
    if not raw_config:
        return None
    try:
        return json.loads(unescape(raw_config))
    except Exception:
        return None


def _play_type_from_config(video_url, config_type):
    cfg_type = (config_type or "").strip().lower()
    if cfg_type == "hls":
        return "m3u8"
    detected = _detect_play_type(video_url)
    if detected != "unknown":
        return detected
    if cfg_type in ("mp4", "webm", "flv"):
        return cfg_type
    return "unknown"


def _extract_style_bg_url(style_text):
    if not style_text:
        return ""
    match = re.search(r'background(?:-image)?\s*:\s*url\((["\']?)([^)"\']+)\1\)', style_text, re.I)
    return match.group(2).strip() if match else ""


def _extract_cover_from_scripts(el, base_url):
    if not el:
        return ""
    # Some sites inject real cover URLs through inline JavaScript instead of <img>.
    patterns = [
        re.compile(r'loadBannerDirect\(\s*["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^"\']*)?)["\']', re.I),
        re.compile(r'["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^"\']*)?)["\']', re.I),
    ]
    candidates = []
    seen = set()
    for script in el.find_all("script"):
        text = script.string or script.get_text() or ""
        if not text:
            continue
        if "loadImage(" in text and any(token in text for token in ("foot-menu-icon", "foot-contact-icon")):
            continue
        for pattern in patterns:
            for match in pattern.finditer(text):
                candidate = _abs_url(match.group(1), base_url)
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)
    if not candidates:
        return ""
    candidates.sort(key=_score_image_url, reverse=True)
    for candidate in candidates:
        if not _is_placeholder_image(candidate):
            return candidate
    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def _extract_cover_from_raw_html(html, base_url):
    if not html:
        return ""
    candidates = []
    seen = set()
    patterns = [
        re.compile(r'https?://[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s"\'<>]*)?', re.I),
        re.compile(r'//[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s"\'<>]*)?', re.I),
    ]
    for pattern in patterns:
        for match in pattern.finditer(html):
            candidate = _abs_url(match.group(0), base_url)
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    if not candidates:
        return ""
    candidates.sort(key=_score_image_url, reverse=True)
    for candidate in candidates:
        if not _is_placeholder_image(candidate):
            return candidate
    return candidates[0]


def _get_cover_candidates(el, base_url):
    candidates = []
    if not el:
        return candidates
    if getattr(el, "name", None) == "img":
        src = _get_img_src(el)
        if src:
            candidates.append(_abs_url(src, base_url))
    for attr in ("poster", "data-poster", "data-cover", "data-pic", "data-bg", "data-background", "data-image"):
        val = el.get(attr, "")
        if val and not str(val).startswith("data:"):
            candidates.append(_abs_url(val, base_url))
    bg_url = _extract_style_bg_url(el.get("style", ""))
    if bg_url:
        candidates.append(_abs_url(bg_url, base_url))
    img = el.find("img") if hasattr(el, "find") else None
    if img:
        src = _get_img_src(img)
        if src:
            candidates.append(_abs_url(src, base_url))
    return [c for c in candidates if c]


def _is_placeholder_image(url):
    lower = (url or "").lower()
    return any(pattern in lower for pattern in PLACEHOLDER_IMAGE_PATTERNS)


def _score_image_url(url):
    lower = (url or "").lower()
    score = 0
    if lower.startswith("http://") or lower.startswith("https://"):
        score += 2
    if any(lower.endswith(ext) or f"{ext}?" in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        score += 2
    if not _is_placeholder_image(lower):
        score += 4
    return score


def _pick_best_cover(soup, base_url):
    article = soup.find("article") or soup.find("div", class_=re.compile(r"content|post|article", re.I)) or soup
    selectors = [
        ".dplayer", "[poster]", "[data-cover]", "[data-pic]",
        ".post-thumbnail img", ".entry-thumbnail img", ".post img", "img",
    ]
    candidates = []
    seen = set()
    for selector in selectors:
        for el in article.select(selector):
            for url in _get_cover_candidates(el, base_url):
                if url not in seen:
                    seen.add(url)
                    candidates.append(url)
    if not candidates:
        return _extract_cover_from_scripts(article, base_url)
    candidates.sort(key=_score_image_url, reverse=True)
    for url in candidates:
        if not _is_placeholder_image(url):
            return url
    script_cover = _extract_cover_from_scripts(article, base_url)
    if script_cover:
        return script_cover
    raw_cover = _extract_cover_from_raw_html(str(article), base_url)
    if raw_cover:
        return raw_cover
    return ""


def _clean_tag(tag):
    tag = (tag or "").strip().strip("#").strip()
    return tag[:30] if tag else ""


def _merge_tags(*groups):
    merged = []
    seen = set()
    for group in groups:
        for tag in group or []:
            cleaned = _clean_tag(tag)
            lowered = cleaned.lower()
            if cleaned and lowered not in seen:
                seen.add(lowered)
                merged.append(cleaned)
    return merged


def _extract_tags_from_text(text):
    if not text:
        return []
    parts = re.split(r"[#,，,、/|\s]+", text)
    return [part for part in (_clean_tag(x) for x in parts) if part]


def _extract_page_tags(soup):
    article = soup.find("article") or soup.find("div", class_=re.compile(r"content|post|article", re.I)) or soup
    direct_tags = []
    meta_keywords = soup.find("meta", attrs={"name": "keywords"})
    if meta_keywords:
        direct_tags.extend(_extract_tags_from_text(meta_keywords.get("content", "")))
    for player in article.select(".dplayer[data-video_tag_name]"):
        direct_tags.extend(_extract_tags_from_text(player.get("data-video_tag_name", "")))
    for a in article.find_all("a", rel="tag"):
        direct_tags.append(a.get_text(strip=True))

    merged = _merge_tags(direct_tags)
    if not merged:
        fallback_tags = []
        for p in article.find_all(["p", "span"]):
            text = p.get_text(" ", strip=True)
            if "关键词" in text or "#" in text:
                fallback_tags.extend(_extract_tags_from_text(text))
        merged = _merge_tags(fallback_tags)
    stop_words = {"首页", "更多", "详情", "播放", "下载", "收藏", "分享", "评论", "查看更多", "点击播放"}
    return [tag for tag in merged if tag not in stop_words and not tag.isdigit()]


class GenericAdapter(BaseAdapter):
    name = "generic"

    def extract_items(self, html, base_url, selectors):
        soup = BeautifulSoup(html, "html.parser")
        items = []
        if selectors.get("link"):
            for el in soup.select(selectors["link"]):
                item = self._extract_single(el, base_url, selectors)
                if item and item.get("detail_url"):
                    items.append(item)
        else:
            if _score_as_detail(base_url) >= 3:
                items = self._extract_detail_page_items(soup, base_url)
            else:
                items = self._extract_listing(soup, base_url)
        seen = set()
        unique = []
        for it in items:
            if it["detail_url"] and it["detail_url"] not in seen:
                seen.add(it["detail_url"])
                unique.append(it)
        return unique

    def _extract_detail_meta(self, soup, base_url):
        item = {"detail_url": base_url, "title": "", "cover_url": "", "description": "", "tags": ""}
        for sel in ("h1.entry-title", "h1.post-title", "h1"):
            t = soup.select_one(sel)
            if t and t.get_text(strip=True):
                item["title"] = t.get_text(strip=True)[:150]
                break
        if not item["title"]:
            tt = soup.find("title")
            if tt: item["title"] = tt.get_text(strip=True)[:150]
        og = {}
        named_meta = {}
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            content = meta.get("content", "")
            if not prop or not content:
                continue
            if prop.startswith("og:"):
                og[prop[3:]] = content
            named_meta[prop.lower()] = content
        if og.get("title") and not item["title"]: item["title"] = og["title"]
        if og.get("description"):
            item["description"] = og["description"][:300]
        elif named_meta.get("description"):
            item["description"] = named_meta["description"][:300]

        meta_cover = ""
        for key in ("image",):
            if og.get(key):
                meta_cover = _abs_url(og[key], base_url)
                break
        if not meta_cover:
            for key in ("twitter:image", "thumbnail", "thumbnailurl"):
                if named_meta.get(key):
                    meta_cover = _abs_url(named_meta[key], base_url)
                    break
        picked_cover = _pick_best_cover(soup, base_url)
        if picked_cover and not _is_placeholder_image(picked_cover):
            item["cover_url"] = picked_cover
        else:
            script_cover = _extract_cover_from_scripts(soup, base_url)
            if script_cover and not _is_placeholder_image(script_cover):
                item["cover_url"] = script_cover
        if not item["cover_url"] and meta_cover and not _is_placeholder_image(meta_cover):
            item["cover_url"] = meta_cover
        if not item["cover_url"]:
            item["cover_url"] = _extract_cover_from_raw_html(str(soup), base_url)
        if not item["description"]:
            for p in (soup.find("article") or soup).find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 20: item["description"] = text[:300]; break
        tags = _extract_page_tags(soup)
        if tags:
            item["tags"] = ",".join(tags[:15])
        return item

    def _extract_detail_page_items(self, soup, base_url):
        page_meta = self._extract_detail_meta(soup, base_url)
        player_items = self._extract_dplayer_items(soup, base_url, page_meta)
        if player_items:
            return player_items
        return [page_meta]

    def _extract_dplayer_items(self, soup, base_url, page_meta=None):
        page_meta = page_meta or self._extract_detail_meta(soup, base_url)
        players = soup.select(".dplayer[data-config]")
        items = []
        for index, player in enumerate(players, start=1):
            config = _load_player_config(player.get("data-config", ""))
            if not config:
                continue
            video_info = config.get("video") or {}
            video_url = _abs_url(video_info.get("url", ""), base_url)
            if not video_url:
                continue
            player_id = (player.get("data-video_id") or "").strip()
            player_title = (player.get("data-video_title") or "").strip()
            item = dict(page_meta)
            item["detail_url"] = _build_player_detail_url(base_url, player_id, index)
            item["play_url"] = video_url
            item["play_type"] = _play_type_from_config(video_url, video_info.get("type"))
            if player_title:
                item["title"] = player_title[:150]
            player_tags = _extract_tags_from_text(player.get("data-video_tag_name", ""))
            merged_tags = _merge_tags(player_tags, (item.get("tags", "") or "").split(","))
            if merged_tags:
                item["tags"] = ",".join(merged_tags[:15])
            config_cover = video_info.get("pic") or video_info.get("cover") or video_info.get("poster") or config.get("pic")
            if config_cover:
                resolved_cover = _abs_url(config_cover, base_url)
                if resolved_cover and not _is_placeholder_image(resolved_cover):
                    item["cover_url"] = resolved_cover
            items.append(item)
        return items

    def _extract_listing(self, soup, base_url):
        items = []
        parsed_base = urlparse(base_url)
        for el in soup.find_all(["a", "div", "li", "article"], recursive=True):
            a_tag = el if el.name == "a" else el.find("a", href=True)
            if not a_tag: continue
            href = a_tag.get("href", "")
            if not href or href.startswith(("#", "javascript:")): continue
            full_url = _abs_url(href, base_url)
            parsed = urlparse(full_url)
            if parsed.hostname and parsed_base.hostname and parsed.hostname != parsed_base.hostname: continue
            if re.search(r"\.(css|js|png|gif|svg|ico|woff|ttf)(\?|$)", href, re.I): continue
            path_lower = parsed.path.lower()
            if any(path_lower.startswith(prefix) for prefix in SKIP_PREFIXES): continue
            if _score_as_detail(full_url) < 3: continue
            classes = " ".join(el.get("class", [])).lower()
            img = el.find("img")
            cover = ""
            for candidate in _get_cover_candidates(el, base_url):
                if not _is_placeholder_image(candidate):
                    cover = candidate
                    break
            if not cover:
                cover = _extract_cover_from_scripts(el, base_url)
            if not (img or cover or any(token in classes for token in ("post-card", "thumb", "cover", "image"))):
                continue
            title = ""
            for tag in ("h1","h2","h3","h4","h5","span","p"):
                t = el.find(tag)
                if t and t.get_text(strip=True): title = t.get_text(strip=True)[:100]; break
            if not title: title = a_tag.get("title", "") or a_tag.get_text(strip=True)[:100]
            if not title: continue
            desc = ""
            p = el.find("p")
            if p: desc = p.get_text(strip=True)[:300]
            items.append({"detail_url": full_url, "title": title, "cover_url": cover, "description": desc})
        return items

    def _extract_single(self, el, base_url, selectors):
        item = {"detail_url": "", "title": "", "cover_url": "", "description": ""}
        href = el.get("href") if el.name == "a" else ""
        if not href:
            a = el.find("a"); href = a.get("href", "") if a else ""
        item["detail_url"] = _abs_url(href, base_url)
        if selectors.get("title"):
            t = el.select_one(selectors["title"]); item["title"] = t.get_text(strip=True) if t else ""
        if not item["title"]:
            t = el.find(["h1","h2","h3","h4","h5"])
            if t: item["title"] = t.get_text(strip=True)
            elif el.get("title"): item["title"] = el["title"]
            elif el.get_text(strip=True): item["title"] = el.get_text(strip=True)[:100]
        if selectors.get("cover"):
            c = el.select_one(selectors["cover"])
            if c: item["cover_url"] = _abs_url(_get_img_src(c), base_url)
        if not item["cover_url"]:
            img = el.find("img")
            if img: item["cover_url"] = _abs_url(_get_img_src(img), base_url)
        if selectors.get("desc"):
            d = el.select_one(selectors["desc"]); item["description"] = d.get_text(strip=True)[:300] if d else ""
        if not item["description"]:
            p = el.find("p"); item["description"] = p.get_text(strip=True)[:300] if p else ""
        return item

    def extract_play_url(self, html, base_url):
        """最强版播放链接提取。"""
        soup = BeautifulSoup(html, "html.parser")
        target_fragment = _normalize_player_fragment(urlparse(base_url).fragment)

        players = soup.select(".dplayer[data-config]")
        if players:
            player_items = self._extract_dplayer_items(soup, base_url)
            if player_items:
                if target_fragment:
                    for item in player_items:
                        item_fragment = _normalize_player_fragment(urlparse(item["detail_url"]).fragment)
                        if item_fragment == target_fragment:
                            return item["play_url"], item["play_type"]
                return player_items[0]["play_url"], player_items[0]["play_type"]

        # 1. video/source
        video = soup.find("video")
        if video:
            src = video.get("src") or ""
            if not src:
                s = video.find("source")
                if s: src = s.get("src", "")
            if src: return _abs_url(src, base_url), _detect_play_type(src)
        # 2. a tags
        for a in soup.find_all("a", href=True):
            if re.search(r"\.(mp4|m3u8|webm|flv)(\?|$)", a["href"], re.I):
                return _abs_url(a["href"], base_url), _detect_play_type(a["href"])
        # 3. source tags
        for source in soup.find_all("source", src=True):
            if re.search(r"\.(mp4|m3u8|webm|flv)(\?|$)", source["src"], re.I):
                return _abs_url(source["src"], base_url), _detect_play_type(source["src"])
        # 4. JavaScript
        url_pat = re.compile(r"https?://\S+\.(mp4|m3u8|webm|flv)", re.I)
        for script in soup.find_all("script"):
            text = script.string or ""
            if not text: continue
            match = url_pat.search(text)
            if match: return _abs_url(match.group(0), base_url), _detect_play_type(match.group(0))
            # JSON url fields
            for pat in (r'"(?:url|file|source|src|video|playurl)"\s*:\s*"([^"]+)"',):
                match = re.search(pat, text, re.I)
                if match:
                    c = match.group(1)
                    if re.search(r"\.(mp4|m3u8|webm|flv)", c, re.I):
                        return _abs_url(c, base_url), _detect_play_type(c)
        # 5. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    for key in ("embedUrl", "contentUrl"):
                        val = data.get(key, "")
                        if isinstance(val, str) and re.search(r"\.(mp4|m3u8|webm|flv)", val, re.I):
                            return _abs_url(val, base_url), _detect_play_type(val)
            except: pass
        # 6. iframe
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if src and not src.startswith("about:"):
                return _abs_url(src, base_url), "iframe"
        # 7. data-url
        for el in soup.find_all(attrs={"data-url": True}):
            c = el.get("data-url", "")
            if re.search(r"\.(mp4|m3u8|webm|flv)", c, re.I):
                return _abs_url(c, base_url), _detect_play_type(c)
        return "", "unknown"


AdapterRegistry.register(GenericAdapter)
