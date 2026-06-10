/* app.js - frontend logic */
(function(){
"use strict";

const API = "";
const PAGE_SIZE = 30;
const MANAGEMENT_TABS = new Set(["sources", "export", "adapters"]);
const state = {
    currentView: "grid",
    sourcesById: {}
};

function $(selector){ return document.querySelector(selector); }
function $$(selector){ return document.querySelectorAll(selector); }
function esc(value){
    return value ? String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;") : "";
}
function excerpt(value, limit){
    const text = String(value || "").replace(/\s+/g, " ").trim();
    const max = limit || 140;
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
}
function splitTags(value){
    return String(value || "")
        .split(",")
        .map(function(item){ return item.trim(); })
        .filter(Boolean);
}
function coverProxyUrl(videoId){
    return videoId ? API + "/api/cover?vid=" + encodeURIComponent(videoId) : "";
}
function sortLabel(value){
    return ({
        updated_at: "最新更新",
        created_at: "最新添加",
        title: "按标题",
        source_name: "按来源"
    })[value] || "最新更新";
}
function formatPlayType(value){
    return ({
        m3u8: "M3U8",
        mp4: "MP4",
        webm: "WEBM",
        iframe: "网页内嵌",
        unknown: "待解析"
    })[value] || String(value || "待解析").toUpperCase();
}
function deriveSourceDisplayName(name, url, id){
    const rawName = String(name || "").trim();
    if(rawName && !/^\d+$/.test(rawName)) return rawName;
    try{
        if(url){
            const host = new URL(url).hostname.replace(/^www\./, "");
            if(host) return host;
        }
    }catch(err){}
    return id ? "源 " + id : (rawName || "未知来源");
}
function formatSourceLabel(sourceName, sourceId){
    const meta = state.sourcesById[sourceId] || {};
    return deriveSourceDisplayName(sourceName || meta.name, meta.url, sourceId);
}

async function api(path, options){
    const response = await fetch(API + path, {
        headers: {"Content-Type": "application/json"},
        ...(options || {})
    });
    if(!response.ok){
        const error = await response.json().catch(function(){ return {}; });
        throw new Error(error.detail || response.statusText);
    }
    return response.json();
}

function toast(message, isError){
    const node = document.createElement("div");
    node.className = "toast" + (isError ? " error" : "");
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(function(){ node.remove(); }, 4000);
}

function closeMoreMenu(){
    const wrap = document.querySelector(".more-wrap");
    const button = document.getElementById("moreMenuBtn");
    if(wrap) wrap.classList.remove("open");
    if(button) button.setAttribute("aria-expanded", "false");
}

function setActiveNavigation(tab){
    document.querySelectorAll(".nav-btn[data-tab]").forEach(function(button){
        button.classList.toggle("active", button.dataset.tab === tab);
    });
    document.querySelectorAll(".more-item").forEach(function(button){
        button.classList.toggle("active", button.dataset.tab === tab);
    });

    const moreButton = document.getElementById("moreMenuBtn");
    if(moreButton){
        moreButton.classList.toggle("active", MANAGEMENT_TABS.has(tab));
    }
}

function showSection(tab){
    document.querySelectorAll(".tab-content").forEach(function(section){
        section.classList.toggle("active", section.id === "tab-" + tab);
    });
    setActiveNavigation(tab);
    closeMoreMenu();

    if(tab === "videos") loadVideos(1).catch(function(err){ toast(err.message, true); });
    if(tab === "favorites") loadFavorites().catch(function(err){ toast(err.message, true); });
    if(tab === "sources") loadSources().catch(function(err){ toast(err.message, true); });
    if(tab === "export") initExport();
    if(tab === "adapters") loadAdapters();
}

function currentFilterValues(){
    return {
        source: ($("#filterSource") || {}).value || "",
        category: ($("#filterCategory") || {}).value || "",
        tag: ($("#filterTag") || {}).value || ""
    };
}

function setFilterState(){
    const values = currentFilterValues();
    const anyActive = !!(values.source || values.category || values.tag);
    const clearButton = document.getElementById("clearFilters");
    if(clearButton) clearButton.style.display = anyActive ? "inline-flex" : "none";
    document.querySelectorAll(".filters select").forEach(function(select){
        select.classList.toggle("active-filter", !!select.value);
    });
}

function filterSummaryText(){
    const values = currentFilterValues();
    const active = [];
    if(values.source) active.push("来源");
    if(values.category) active.push("分类");
    if(values.tag) active.push("标签");
    return active.length ? "已启用 " + active.join(" / ") + " 筛选" : "未启用筛选";
}

function updateResultsState(total, totalPages, page){
    const summary = document.getElementById("resultsSummary");
    const sort = sortLabel((document.getElementById("sortBy") || {}).value || "updated_at");
    const totalText = "共 " + (total || 0) + " 条";
    const pageText = total ? "第 " + (page || 1) + " / " + Math.max(totalPages || 1, 1) + " 页" : "暂无结果";
    if(summary){
        summary.textContent = totalText + " · " + pageText + " · " + sort + " · " + filterSummaryText();
    }
    setFilterState();
}

function applyViewMode(){
    document.querySelectorAll(".video-grid").forEach(function(grid){
        if(grid.id === "videoGrid" || grid.id === "favGrid"){
            grid.classList.toggle("list-view", state.currentView === "list");
        }
    });
    document.getElementById("viewGrid").classList.toggle("active", state.currentView === "grid");
    document.getElementById("viewList").classList.toggle("active", state.currentView === "list");
}

function renderEmptyState(gridId){
    if(gridId === "favGrid"){
        return '<div class="empty-state"><div class="icon">♥</div><h4>还没有收藏内容</h4><p>把想回看的视频先收藏起来，这里会成为你的快速入口。</p></div>';
    }
    return '<div class="empty-state"><div class="icon">⌕</div><h4>没有匹配结果</h4><p>可以试试修改关键词，或者清除部分筛选条件后再看一轮。</p></div>';
}

function renderGrid(gridId, items){
    const grid = document.getElementById(gridId);
    if(!grid) return;
    if(!items.length){
        grid.innerHTML = renderEmptyState(gridId);
        applyViewMode();
        return;
    }

    grid.innerHTML = items.map(function(video){
        const sourceLabel = formatSourceLabel(video.source_name, video.source_id);
        const coverUrl = coverProxyUrl(video.id);
        const canTryCover = !!(video.id && (video.cover_url || video.detail_url));
        return `
        <article class="video-card" data-id="${video.id}" data-play-url="${esc(video.play_url)}" data-play-type="${esc(video.play_type)}" data-detail-url="${esc(video.detail_url)}" data-title="${esc(video.title)}" data-desc="${esc(video.description)}" data-source="${esc(video.source_name)}" data-cover="${esc(coverUrl)}" data-tags="${esc(video.tags)}" data-is-fav="${video.is_favorite ? 1 : 0}">
            <div class="card-media${canTryCover ? "" : " no-cover"}">
                <div class="cover-fallback">NO COVER</div>
                ${canTryCover ? `<img class="cover" src="${esc(coverUrl)}" loading="lazy" decoding="async" onerror="this.style.display='none'; this.parentElement.classList.add('no-cover')" onload="this.style.opacity=1" style="opacity:0;transition:opacity .24s ease">` : ""}
                <span class="source-pill" title="${esc(sourceLabel)}">${esc(sourceLabel)}</span>
                <button class="fav-btn ${video.is_favorite ? "active" : ""}" type="button" data-vid="${video.id}" aria-label="切换收藏">${video.is_favorite ? "♥" : "♡"}</button>
                <span class="card-cue">查看详情</span>
            </div>
            <div class="info">
                <h3 class="title">${esc(video.title)}</h3>
            </div>
        </article>`;
    }).join("");

    applyViewMode();
}

function renderPage(id, current, total, handler){
    const node = document.getElementById(id);
    if(!node) return;
    if(total <= 1){
        node.innerHTML = "";
        return;
    }

    let html = "";
    for(let page = Math.max(1, current - 3); page <= Math.min(total, current + 3); page += 1){
        html += `<button class="${page === current ? "active" : ""}" data-page="${page}" type="button">${page}</button>`;
    }
    node.innerHTML = html;
    node.querySelectorAll("button").forEach(function(button){
        button.addEventListener("click", function(){
            handler(Number(button.dataset.page));
        });
    });
}

function showSkeleton(gridId, count){
    const grid = document.getElementById(gridId);
    if(!grid) return;
    let html = "";
    for(let i = 0; i < count; i += 1){
        html += '<div class="video-card skeleton-card"><div class="card-media skeleton"></div><div class="info"><div class="skeleton-title skeleton"></div><div class="skeleton-desc skeleton"></div><div class="skeleton-meta skeleton"></div></div></div>';
    }
    grid.innerHTML = html;
    applyViewMode();
}

async function loadVideos(page){
    const params = new URLSearchParams();
    const keyword = ($("#searchInput") || {}).value ? $("#searchInput").value.trim() : "";
    if(keyword) params.set("keyword", keyword);
    if($("#filterSource").value) params.set("source_id", $("#filterSource").value);
    if($("#filterCategory").value) params.set("category", $("#filterCategory").value);
    if($("#filterTag").value) params.set("tag", $("#filterTag").value);
    if($("#sortBy").value) params.set("sort", $("#sortBy").value);
    params.set("page", page || 1);
    params.set("page_size", PAGE_SIZE);

    showSkeleton("videoGrid", 12);
    const data = await api("/api/videos?" + params.toString());
    renderGrid("videoGrid", data.items);
    renderPage("pagination", data.page, data.total_pages, loadVideos);
    updateResultsState(data.total, data.total_pages, data.page);
}

async function loadFavorites(){
    const data = await api("/api/videos?favorite=1&page_size=100");
    renderGrid("favGrid", data.items);
}

async function loadFilters(){
    const previous = currentFilterValues();
    if(!Object.keys(state.sourcesById).length){
        const sourceList = await api("/api/sources");
        sourceList.forEach(function(source){
            state.sourcesById[source.id] = source;
        });
    }
    const data = await api("/api/videos/filters");

    const source = document.getElementById("filterSource");
    const category = document.getElementById("filterCategory");
    const tag = document.getElementById("filterTag");

    source.innerHTML = '<option value="">全部来源</option>';
    category.innerHTML = '<option value="">全部分类</option>';
    tag.innerHTML = '<option value="">全部标签</option>';

    data.sources.forEach(function(item){
        const meta = state.sourcesById[item.id] || {};
        const label = deriveSourceDisplayName(item.name || meta.name, meta.url, item.id);
        source.innerHTML += `<option value="${item.id}">${esc(label)}</option>`;
    });
    data.categories.forEach(function(item){
        category.innerHTML += `<option value="${esc(item)}">${esc(item)}</option>`;
    });
    data.tags.forEach(function(item){
        tag.innerHTML += `<option value="${esc(item)}">${esc(item)}</option>`;
    });

    if([].slice.call(source.options).some(function(option){ return option.value === previous.source; })) source.value = previous.source;
    if([].slice.call(category.options).some(function(option){ return option.value === previous.category; })) category.value = previous.category;
    if([].slice.call(tag.options).some(function(option){ return option.value === previous.tag; })) tag.value = previous.tag;

    setFilterState();
}

function openDetail(card){
    const data = {
        id: card.dataset.id,
        playUrl: card.dataset.playUrl,
        playType: card.dataset.playType,
        detailUrl: card.dataset.detailUrl,
        title: card.dataset.title,
        desc: card.dataset.desc,
        source: card.dataset.source,
        cover: card.dataset.cover,
        tags: card.dataset.tags,
        isFav: card.dataset.isFav === "1"
    };

    const tagHtml = splitTags(data.tags).slice(0, 6).map(function(tag){
        return `<span>${esc(tag)}</span>`;
    }).join("");

    document.getElementById("detailTitle").textContent = data.title;
    document.getElementById("detailDesc").textContent = excerpt(data.desc || "暂无简介", 240);
    document.getElementById("detailCover").onerror = function(){ this.style.display = "none"; };
    document.getElementById("detailCover").src = data.cover || "";
    document.getElementById("detailCover").style.display = data.cover ? "block" : "none";
    document.getElementById("detailMeta").innerHTML = `<span>来源：${esc(data.source || "-")}</span><span>播放：${esc(formatPlayType(data.playType))}</span>${tagHtml}`;
    document.getElementById("detailLink").href = data.detailUrl || "#";
    document.getElementById("detailLink").style.display = data.detailUrl ? "inline-flex" : "none";
    document.getElementById("detailFavBtn").textContent = data.isFav ? "已收藏" : "收藏";

    document.getElementById("detailFavBtn").onclick = async function(){
        const result = await api("/api/videos/" + data.id + "/favorite", {method: "PUT"});
        data.isFav = !!result.is_favorite;
        card.dataset.isFav = data.isFav ? "1" : "0";
        document.getElementById("detailFavBtn").textContent = data.isFav ? "已收藏" : "收藏";
        const cardFav = card.querySelector(".fav-btn");
        if(cardFav){
            cardFav.classList.toggle("active", data.isFav);
            cardFav.textContent = data.isFav ? "♥" : "♡";
        }
        updateTabBadges();
        if(document.getElementById("tab-favorites").classList.contains("active") && !data.isFav){
            loadFavorites().catch(function(){});
        }
    };

    document.getElementById("detailPlayBtn").onclick = async function(){
        document.getElementById("detailModal").classList.remove("open");
        try{
            const refreshed = await api("/api/videos/" + data.id + "/play-url", {method: "POST"});
            if(refreshed.play_url){
                data.playUrl = refreshed.play_url;
                data.playType = refreshed.play_type || data.playType;
            }
        }catch(err){}
        Player.open(data);
        api("/api/videos/" + data.id + "/watch?status=watched", {method: "PUT"}).catch(function(){});
    };

    document.getElementById("detailModal").classList.add("open");
}

function updateTabBadges(){
    fetch("/api/videos?favorite=1&page_size=1")
        .then(function(response){ return response.json(); })
        .then(function(data){
            const button = document.querySelector('.nav-btn[data-tab="favorites"]');
            if(!button) return;
            const existing = button.querySelector(".badge");
            if(existing) existing.remove();
            if(data.total > 0){
                const badge = document.createElement("span");
                badge.className = "badge";
                badge.textContent = data.total;
                button.appendChild(badge);
            }
        })
        .catch(function(){});
}

async function loadSources(){
    const sources = await api("/api/sources");
    state.sourcesById = {};
    sources.forEach(function(source){
        state.sourcesById[source.id] = source;
    });
    document.getElementById("sourceList").innerHTML = sources.map(function(source){
        const shortUrl = source.url.length > 40 ? source.url.slice(0, 40) + "…" : source.url;
        return `<tr>
            <td>${esc(source.name)}</td>
            <td>${esc(source.category)}</td>
            <td><a href="${esc(source.url)}" target="_blank">${esc(shortUrl)}</a></td>
            <td>${source.refresh_interval}</td>
            <td><span class="enabled-dot ${source.enabled ? "on" : "off"}"></span></td>
            <td>
                <button class="btn-secondary btn-small edit-source" type="button" data-id="${source.id}">编辑</button>
                <button class="btn-secondary btn-small scan-one" type="button" data-id="${source.id}">扫描</button>
                <button class="btn-danger btn-small del-source" type="button" data-id="${source.id}">删除</button>
            </td>
        </tr>`;
    }).join("");

    await loadFilters().catch(function(){});
}

function isLoopbackHost(hostname){
    return ["127.0.0.1", "localhost", "::1", "[::1]"].includes(String(hostname || "").toLowerCase());
}

function setExportActionUrls(tvboxUrl, m3uUrl, miraplayUrl){
    document.getElementById("openTvboxBtn").dataset.url = tvboxUrl;
    document.getElementById("copyTvboxBtn").dataset.url = tvboxUrl;
    document.getElementById("openM3uBtn").dataset.url = m3uUrl;
    document.getElementById("copyM3uBtn").dataset.url = m3uUrl;
    document.getElementById("openMiraplayBtn").dataset.url = miraplayUrl;
    document.getElementById("copyMiraplayBtn").dataset.url = miraplayUrl;
}

function setMaintenanceResult(message, isError){
    const node = document.getElementById("maintenanceResult");
    if(!node) return;
    if(!message){
        node.style.display = "none";
        node.textContent = "";
        node.style.borderColor = "";
        node.style.color = "";
        return;
    }
    node.style.display = "block";
    node.textContent = message;
    node.style.borderColor = isError ? "rgba(216,111,111,.32)" : "";
    node.style.color = isError ? "#f0c2c2" : "";
}

function summarizeMaintenance(data){
    if(!data) return "维护操作已完成";
    if(data.action === "cover_backfill"){
        return "封面回填完成：更新 " + (data.updated_rows || 0) + " 条，剩余空封面 " + (data.remaining_rows || 0) + " 条。";
    }
    if(data.action === "cleanup_dirty"){
        return "脏数据清理完成：删除 " + (data.deleted_rows || 0) + " 条错误记录。";
    }
    return "维护操作已完成";
}

async function runMaintenance(path, buttonId, confirmText){
    if(pollTimer){
        toast("请先等待当前扫描完成", true);
        return;
    }
    if(!confirm(confirmText)) return;

    const button = document.getElementById(buttonId);
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "处理中...";
    setMaintenanceResult("处理中，请稍候…", false);

    try{
        const data = await api(path, {method: "POST"});
        const message = summarizeMaintenance(data);
        setMaintenanceResult(message, false);
        toast(message);
        await loadSources().catch(function(){});
        if(document.getElementById("tab-videos").classList.contains("active")){
            await loadVideos(1).catch(function(){});
        }
        if(document.getElementById("tab-favorites").classList.contains("active")){
            await loadFavorites().catch(function(){});
        }
        updateTabBadges();
    }catch(err){
        const message = "维护失败：" + err.message;
        setMaintenanceResult(message, true);
        toast(message, true);
    }finally{
        button.disabled = false;
        button.textContent = originalText;
    }
}

async function initExport(){
    let base = location.origin;
    let note = "当前已使用可访问地址，可直接复制给同一网络设备。";

    if(isLoopbackHost(location.hostname)){
        note = "当前页面通过本机地址打开，正在尝试切换为公网或局域网地址。";
        try{
            const data = await api("/api/export/origins");
            if(data.public_origin){
                base = data.public_origin;
                note = "已检测到公网 HTTPS 订阅地址，可直接用于 TVBox 外部导入。";
            }else if(data.preferred_origin){
                base = data.preferred_origin;
                note = "已自动切换为局域网地址，同一网络下的手机、电视盒子可直接使用。";
            }else{
                note = "未检测到可用局域网地址，当前仍显示本机地址。";
            }
        }catch(err){
            note = "无法获取局域网地址，当前仍显示本机地址。";
        }
    }

    const tvboxUrl = base + "/api/tvbox";
    const m3uUrl = base + "/api/m3u";
    const miraplayUrl = base + "/api/miraplay/index.js.md5";

    document.getElementById("exportOriginNote").textContent = note;
    document.getElementById("tvboxUrl").textContent = tvboxUrl;
    document.getElementById("m3uUrl").textContent = m3uUrl;
    document.getElementById("miraplayUrl").textContent = miraplayUrl;
    setExportActionUrls(tvboxUrl, m3uUrl, miraplayUrl);
}

function loadAdapters(){
    fetch("/api/adapters")
        .then(function(response){ return response.json(); })
        .then(function(list){
            document.getElementById("adapterList").innerHTML = list.map(function(adapter){
                return `<tr>
                    <td>${esc(adapter.name)}</td>
                    <td>${esc(adapter.url_pattern)}</td>
                    <td>${esc(adapter.list_selector || "-")}</td>
                    <td><span class="enabled-dot ${adapter.enabled ? "on" : "off"}"></span></td>
                    <td>
                        <button class="btn-secondary btn-small edit-adapter" type="button" data-id="${adapter.id}">编辑</button>
                        <button class="btn-danger btn-small del-adapter" type="button" data-id="${adapter.id}">删除</button>
                    </td>
                </tr>`;
            }).join("");
        });
}

let pollTimer = null;

async function startScan(url){
    const response = await api(url, {method: "POST"});
    if(response.ok){
        toast("扫描已启动");
        startPolling();
    }else{
        toast(response.message || "启动失败", true);
    }
}

function stopPolling(){
    if(pollTimer){
        clearInterval(pollTimer);
        pollTimer = null;
    }
    document.querySelectorAll(".scan-one, #scanAllBtn").forEach(function(button){
        button.textContent = button.id === "scanAllBtn" ? "扫描全部" : "扫描";
        button.classList.remove("btn-danger");
        button.classList.add("btn-secondary");
    });
}

function startPolling(){
    if(pollTimer) return;
    document.getElementById("scanStatus").style.display = "flex";
    pollTimer = setInterval(async function(){
        try{
            const status = await api("/api/scan/status");
            if(status.running){
                document.getElementById("scanText").textContent = status.source_name + " · " + status.pages_crawled + " 页 / " + status.videos_found + " 视频";
                document.getElementById("scanBar").style.width = Math.min(100, status.pages_crawled / 50) + "%";
                document.querySelectorAll(".scan-one, #scanAllBtn").forEach(function(button){
                    button.textContent = "停止 (" + status.pages_crawled + "页)";
                    button.classList.add("btn-danger");
                    button.classList.remove("btn-secondary");
                });
                return;
            }

            stopPolling();
            document.getElementById("scanStatus").style.display = "none";
            if(status.done){
                if(status.stopped) toast("扫描已停止：共 " + status.pages_crawled + " 页，新增 " + status.new_added);
                else if(status.error) toast("扫描失败：" + status.error, true);
                else toast("扫描完成：新增 " + status.new_added + "，更新 " + status.updated);
                loadVideos(1).catch(function(){});
                loadSources().catch(function(){});
            }
        }catch(err){}
    }, 2000);
}

function bindNavigation(){
    document.querySelectorAll("[data-tab]").forEach(function(button){
        button.addEventListener("click", function(){
            showSection(button.dataset.tab);
        });
    });

    const moreButton = document.getElementById("moreMenuBtn");
    moreButton.addEventListener("click", function(event){
        event.stopPropagation();
        const wrap = document.querySelector(".more-wrap");
        const open = wrap.classList.toggle("open");
        moreButton.setAttribute("aria-expanded", open ? "true" : "false");
    });

    document.addEventListener("click", function(event){
        if(!event.target.closest(".more-wrap")) closeMoreMenu();
    });
}

function bindSearch(){
    let searchTimer = null;
    const input = document.getElementById("searchInput");

    document.getElementById("searchBtn").addEventListener("click", function(){
        clearTimeout(searchTimer);
        showSection("videos");
    });

    input.addEventListener("keydown", function(event){
        if(event.key === "Enter"){
            clearTimeout(searchTimer);
            showSection("videos");
            return;
        }
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function(){
            if(document.getElementById("tab-videos").classList.contains("active")){
                loadVideos(1).catch(function(){});
            }
        }, 500);
    });
}

function bindFilters(){
    ["filterSource", "filterCategory", "filterTag", "sortBy"].forEach(function(id){
        document.getElementById(id).addEventListener("change", function(){
            loadVideos(1).catch(function(err){ toast(err.message, true); });
        });
    });

    document.getElementById("clearFilters").addEventListener("click", function(){
        document.getElementById("filterSource").value = "";
        document.getElementById("filterCategory").value = "";
        document.getElementById("filterTag").value = "";
        setFilterState();
        loadVideos(1).catch(function(err){ toast(err.message, true); });
    });
}

function bindCardClicks(){
    document.addEventListener("click", async function(event){
        const favButton = event.target.closest(".fav-btn");
        if(favButton){
            event.stopPropagation();
            const result = await api("/api/videos/" + favButton.dataset.vid + "/favorite", {method: "PUT"});
            favButton.classList.toggle("active", !!result.is_favorite);
            favButton.textContent = result.is_favorite ? "♥" : "♡";
            const card = favButton.closest(".video-card");
            if(card) card.dataset.isFav = result.is_favorite ? "1" : "0";
            updateTabBadges();
            if(document.getElementById("tab-favorites").classList.contains("active") && !result.is_favorite){
                loadFavorites().catch(function(){});
            }
            return;
        }

        const card = event.target.closest(".video-card");
        if(card) openDetail(card);
    });
}

function bindDetailModal(){
    document.getElementById("detailClose").addEventListener("click", function(){
        document.getElementById("detailModal").classList.remove("open");
    });
    document.getElementById("detailModal").addEventListener("click", function(event){
        if(event.target === document.getElementById("detailModal")){
            document.getElementById("detailModal").classList.remove("open");
        }
    });
}

function bindSourceActions(){
    document.getElementById("addSourceBtn").addEventListener("click", function(){
        document.getElementById("sourceModalTitle").textContent = "添加视频源";
        document.getElementById("sourceForm").reset();
        document.getElementById("sourceId").value = "";
        document.getElementById("sourceEnabled").checked = true;
        document.getElementById("sourceModal").classList.add("open");
    });

    document.getElementById("sourceModalCancel").addEventListener("click", function(){
        document.getElementById("sourceModal").classList.remove("open");
    });

    document.addEventListener("click", async function(event){
        if(event.target.classList.contains("edit-source")){
            const source = await api("/api/sources/" + event.target.dataset.id);
            document.getElementById("sourceModalTitle").textContent = "编辑视频源";
            document.getElementById("sourceId").value = source.id;
            document.getElementById("sourceName").value = source.name;
            document.getElementById("sourceCategory").value = source.category;
            document.getElementById("sourceUrl").value = source.url;
            document.getElementById("sourceInterval").value = source.refresh_interval;
            document.getElementById("sourceAdapter").value = source.adapter_type;
            document.getElementById("selectorTitle").value = source.selector_title;
            document.getElementById("selectorCover").value = source.selector_cover;
            document.getElementById("selectorLink").value = source.selector_link;
            document.getElementById("selectorDesc").value = source.selector_desc;
            document.getElementById("sourceEnabled").checked = !!source.enabled;
            document.getElementById("sourceModal").classList.add("open");
        }

        if(event.target.classList.contains("del-source")){
            if(!confirm("确定删除这个视频源吗？该网站已扫描的视频内容也会一并删除。")) return;
            await api("/api/sources/" + event.target.dataset.id, {method: "DELETE"});
            toast("已删除视频源及其扫描内容");
            await loadSources();
            await loadVideos(1).catch(function(){});
            await loadFavorites().catch(function(){});
        }
    });

    document.getElementById("sourceForm").addEventListener("submit", async function(event){
        event.preventDefault();
        const id = document.getElementById("sourceId").value;
        const body = {
            name: document.getElementById("sourceName").value,
            category: document.getElementById("sourceCategory").value,
            url: document.getElementById("sourceUrl").value,
            refresh_interval: Number(document.getElementById("sourceInterval").value) || 3600,
            adapter_type: document.getElementById("sourceAdapter").value,
            selector_title: document.getElementById("selectorTitle").value,
            selector_cover: document.getElementById("selectorCover").value,
            selector_link: document.getElementById("selectorLink").value,
            selector_desc: document.getElementById("selectorDesc").value,
            enabled: document.getElementById("sourceEnabled").checked ? 1 : 0
        };

        if(id){
            await api("/api/sources/" + id, {method: "PUT", body: JSON.stringify(body)});
            toast("已更新");
        }else{
            await api("/api/sources", {method: "POST", body: JSON.stringify(body)});
            toast("已添加");
        }

        document.getElementById("sourceModal").classList.remove("open");
        loadSources().catch(function(err){ toast(err.message, true); });
    });
}

function bindScanActions(){
    document.addEventListener("click", function(event){
        if(event.target.classList.contains("scan-one")){
            if(pollTimer){
                api("/api/scan/stop", {method: "POST"}).then(function(){ toast("停止信号已发送"); });
                return;
            }
            startScan("/api/scan/" + event.target.dataset.id).catch(function(err){ toast(err.message, true); });
        }
    });

    document.getElementById("scanAllBtn").addEventListener("click", function(){
        if(pollTimer){
            api("/api/scan/stop", {method: "POST"}).then(function(){ toast("停止信号已发送"); });
            return;
        }
        startScan("/api/scan").catch(function(err){ toast(err.message, true); });
    });
}

function bindImportExport(){
    document.getElementById("exportSourcesBtn").addEventListener("click", async function(){
        const data = await api("/api/sources/export");
        const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "video_sources.json";
        link.click();
        URL.revokeObjectURL(url);
        toast("已导出");
    });

    document.getElementById("importSourcesBtn").addEventListener("click", function(){
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".json";
        input.onchange = async function(){
            const file = input.files[0];
            if(!file) return;
            try{
                const text = await file.text();
                const data = JSON.parse(text);
                const result = await api("/api/sources/import", {method: "POST", body: JSON.stringify(data)});
                toast("已导入 " + result.imported + " 个视频源");
                loadSources().catch(function(err){ toast(err.message, true); });
            }catch(err){
                toast("导入失败：" + err.message, true);
            }
        };
        input.click();
    });
}

function bindExportLinks(){
    document.querySelectorAll(".open-export").forEach(function(button){
        button.addEventListener("click", function(){
            const url = button.dataset.url;
            if(url) window.open(url, "_blank");
        });
    });

    document.querySelectorAll(".copy-export").forEach(function(button){
        button.addEventListener("click", async function(){
            const url = button.dataset.url;
            if(!url){
                toast("导出链接尚未准备好", true);
                return;
            }
            try{
                await navigator.clipboard.writeText(url);
                toast("已复制链接");
            }catch(err){
                toast("复制失败：" + err.message, true);
            }
        });
    });
}

function bindMaintenance(){
    document.getElementById("backfillCoversBtn").addEventListener("click", function(){
        runMaintenance(
            "/api/maintenance/cover-backfill",
            "backfillCoversBtn",
            "确认执行封面回填吗？这会扫描源站分页并补齐当前空封面记录。"
        );
    });

    document.getElementById("cleanupDirtyBtn").addEventListener("click", function(){
        runMaintenance(
            "/api/maintenance/cleanup",
            "cleanupDirtyBtn",
            "确认执行脏数据清理吗？这只会删除明显不是视频详情页的错误记录。"
        );
    });
}

function bindViewAndTheme(){
    document.getElementById("viewGrid").addEventListener("click", function(){
        state.currentView = "grid";
        applyViewMode();
    });
    document.getElementById("viewList").addEventListener("click", function(){
        state.currentView = "list";
        applyViewMode();
    });

    if(localStorage.getItem("theme") === "light"){
        document.body.classList.add("light");
    }
    document.getElementById("themeToggle").addEventListener("click", function(){
        document.body.classList.toggle("light");
        localStorage.setItem("theme", document.body.classList.contains("light") ? "light" : "dark");
    });
}

function bindScrollTop(){
    const button = document.getElementById("scrollTop");
    window.addEventListener("scroll", function(){
        button.classList.toggle("show", window.scrollY > 260);
    });
    button.addEventListener("click", function(){
        window.scrollTo({top: 0, behavior: "smooth"});
    });
}

function bindAdapters(){
    document.getElementById("addAdapterBtn").addEventListener("click", function(){
        document.getElementById("adapterModalTitle").textContent = "添加适配器";
        document.getElementById("adapterForm").reset();
        document.getElementById("adapterId").value = "";
        document.getElementById("adapterEnabled").checked = true;
        document.getElementById("adapterModal").classList.add("open");
    });

    document.getElementById("adapterModalCancel").addEventListener("click", function(){
        document.getElementById("adapterModal").classList.remove("open");
    });

    document.addEventListener("click", function(event){
        if(event.target.classList.contains("edit-adapter")){
            fetch("/api/adapters/" + event.target.dataset.id)
                .then(function(response){ return response.json(); })
                .then(function(adapter){
                    document.getElementById("adapterModalTitle").textContent = "编辑适配器";
                    document.getElementById("adapterId").value = adapter.id;
                    document.getElementById("adapterName").value = adapter.name;
                    document.getElementById("adapterUrlPattern").value = adapter.url_pattern;
                    document.getElementById("adapterDesc").value = adapter.description || "";
                    document.getElementById("adapterListSel").value = adapter.list_selector || "";
                    document.getElementById("adapterTitleSel").value = adapter.title_selector || "";
                    document.getElementById("adapterCoverSel").value = adapter.cover_selector || "";
                    document.getElementById("adapterLinkSel").value = adapter.link_selector || "";
                    document.getElementById("adapterDescSel").value = adapter.desc_selector || "";
                    document.getElementById("adapterDetailTitle").value = adapter.detail_title_selector || "";
                    document.getElementById("adapterDetailCover").value = adapter.detail_cover_selector || "";
                    document.getElementById("adapterDetailDesc").value = adapter.detail_desc_selector || "";
                    document.getElementById("adapterPlayPattern").value = adapter.play_url_pattern || "";
                    document.getElementById("adapterEnabled").checked = !!adapter.enabled;
                    document.getElementById("adapterModal").classList.add("open");
                });
        }

        if(event.target.classList.contains("del-adapter")){
            if(confirm("确定删除这个适配器吗？")){
                fetch("/api/adapters/" + event.target.dataset.id, {method: "DELETE"})
                    .then(function(){ toast("已删除"); loadAdapters(); });
            }
        }
    });

    document.getElementById("adapterForm").addEventListener("submit", function(event){
        event.preventDefault();
        const id = document.getElementById("adapterId").value;
        const body = {
            name: document.getElementById("adapterName").value,
            url_pattern: document.getElementById("adapterUrlPattern").value,
            description: document.getElementById("adapterDesc").value,
            list_selector: document.getElementById("adapterListSel").value,
            title_selector: document.getElementById("adapterTitleSel").value,
            cover_selector: document.getElementById("adapterCoverSel").value,
            link_selector: document.getElementById("adapterLinkSel").value,
            desc_selector: document.getElementById("adapterDescSel").value,
            detail_title_selector: document.getElementById("adapterDetailTitle").value,
            detail_cover_selector: document.getElementById("adapterDetailCover").value,
            detail_desc_selector: document.getElementById("adapterDetailDesc").value,
            play_url_pattern: document.getElementById("adapterPlayPattern").value,
            enabled: document.getElementById("adapterEnabled").checked ? 1 : 0
        };
        const url = id ? "/api/adapters/" + id : "/api/adapters";
        const method = id ? "PUT" : "POST";

        fetch(url, {method: method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})
            .then(function(response){ return response.json(); })
            .then(function(){
                toast(id ? "已更新" : "已添加");
                document.getElementById("adapterModal").classList.remove("open");
                loadAdapters();
            });
    });
}

function init(){
    bindNavigation();
    bindSearch();
    bindFilters();
    bindCardClicks();
    bindDetailModal();
    bindSourceActions();
    bindScanActions();
    bindImportExport();
    bindMaintenance();
    bindExportLinks();
    bindViewAndTheme();
    bindScrollTop();
    bindAdapters();

    setTimeout(updateTabBadges, 1000);
    loadFilters()
        .catch(function(){})
        .finally(function(){
            applyViewMode();
            loadVideos(1).catch(function(err){ toast(err.message, true); });
        });
}

init();

})();
