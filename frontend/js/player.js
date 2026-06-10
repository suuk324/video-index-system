/* player.js - multi-format player with lightweight recovery */
const Player = (function () {
    "use strict";

    let hlsInstance = null;
    let activeToken = 0;
    let refreshPromise = null;
    let playbackState = null;

    function open(data) {
        const modal = document.getElementById("playerModal");
        document.getElementById("playerTitle").textContent = data.title || "";
        document.getElementById("playerDesc").textContent = data.desc || "";
        document.getElementById("playerMeta").innerHTML =
            `<span>来源: ${data.source || "-"}</span>` +
            (data.detailUrl ? `<span><a href="${data.detailUrl}" target="_blank" style="color:#7c83ff">查看原网页</a></span>` : "");

        destroy();
        activeToken += 1;
        playbackState = {
            data: {
                id: data.id,
                title: data.title || "",
                desc: data.desc || "",
                source: data.source || "",
                detailUrl: data.detailUrl || "",
                cover: data.cover || "",
                playUrl: data.playUrl || "",
                playType: data.playType || "unknown"
            },
            refreshAttempts: 0,
            mediaRecoveryAttempts: 0
        };

        _renderPlayback(playbackState.data, 0, activeToken);
        modal.classList.add("open");
    }

    function _renderPlayback(data, resumeTime, token) {
        const container = document.getElementById("playerContainer");
        const playUrl = _playbackUrl(data);
        const playType = data.playType || "unknown";

        _cleanupPlayback();

        if (playUrl && playType === "iframe") {
            container.innerHTML = `<iframe src="${esc(playUrl)}" frameborder="0" allowfullscreen style="width:100%;height:100%"></iframe>`;
            return;
        }

        if (playUrl && _isPlayable(playType)) {
            container.innerHTML = '<video controls autoplay playsinline></video>';
            const video = container.querySelector("video");
            if (data.cover) video.poster = data.cover;
            _bindResume(video, resumeTime);

            if (playType === "m3u8" && typeof Hls !== "undefined" && Hls.isSupported()) {
                hlsInstance = new Hls({ maxBufferLength: 30 });
                hlsInstance.loadSource(playUrl);
                hlsInstance.attachMedia(video);
                hlsInstance.on(Hls.Events.ERROR, function (_, errorData) {
                    _handleHlsError(errorData, video, data, token);
                });
            } else {
                video.src = playUrl;
                video.onerror = function () {
                    _refreshPlayUrl(video, data, token);
                };
            }
            return;
        }

        _showFallback(container, data);
    }

    function _isPlayable(type) {
        return ["mp4", "webm", "m3u8", "flv", "mkv", "avi"].includes(type);
    }

    function _playbackUrl(data) {
        if (!data) return "";
        if (data.id && _isPlayable(data.playType || "unknown")) {
            return "/api/play?vid=" + encodeURIComponent(data.id);
        }
        return data.playUrl || "";
    }

    function _bindResume(video, resumeTime) {
        if (!(resumeTime > 0)) return;
        video.addEventListener("loadedmetadata", function restorePosition() {
            video.removeEventListener("loadedmetadata", restorePosition);
            try {
                video.currentTime = resumeTime;
            } catch (err) {}
        });
    }

    function _handleHlsError(errorData, video, data, token) {
        if (!errorData || !errorData.fatal) return;

        // Root cause: authenticated HLS URLs and transient HLS errors were treated as hard failures.
        if (
            errorData.type === Hls.ErrorTypes.MEDIA_ERROR &&
            hlsInstance &&
            playbackState &&
            playbackState.mediaRecoveryAttempts < 1
        ) {
            playbackState.mediaRecoveryAttempts += 1;
            hlsInstance.recoverMediaError();
            return;
        }

        _refreshPlayUrl(video, data, token);
    }

    function _refreshPlayUrl(video, data, token) {
        const container = document.getElementById("playerContainer");
        const resumeTime = video && Number.isFinite(video.currentTime) ? video.currentTime : 0;

        if (!data || !data.id || !playbackState) {
            _showFallback(container, data || {});
            return;
        }
        if (playbackState.refreshAttempts >= 2) {
            _showFallback(container, data);
            return;
        }
        if (refreshPromise) return;

        playbackState.refreshAttempts += 1;
        refreshPromise = fetch("/api/videos/" + data.id + "/play-url", { method: "POST" })
            .then(function (response) {
                if (!response.ok) throw new Error("refresh failed");
                return response.json();
            })
            .then(function (refreshed) {
                refreshPromise = null;
                if (token !== activeToken || !playbackState) return;

                if (refreshed && refreshed.play_url) {
                    data.playUrl = refreshed.play_url;
                    data.playType = refreshed.play_type || data.playType || "unknown";
                    playbackState.data.playUrl = data.playUrl;
                    playbackState.data.playType = data.playType;
                    playbackState.mediaRecoveryAttempts = 0;
                    _renderPlayback(data, resumeTime, token);
                    return;
                }

                _showFallback(container, data);
            })
            .catch(function () {
                refreshPromise = null;
                if (token !== activeToken) return;
                _showFallback(container, data);
            });
    }

    function _showFallback(container, data) {
        const detailUrl = data.detailUrl || "";
        if (detailUrl) {
            container.innerHTML = '<iframe src="' + esc(detailUrl) + '" frameborder="0" allowfullscreen allow="autoplay; fullscreen" style="width:100%;height:100%" id="fallbackFrame"></iframe>';
            var frame = document.getElementById("fallbackFrame");
            frame.onerror = function () {
                container.innerHTML = '<div class="no-play"><p>此视频无法在当前页面内播放</p><p style="font-size:12px;color:#666">原网站限制了嵌入</p><a href="' + esc(detailUrl) + '" target="_blank">前往原网页观看 -></a></div>';
            };
            setTimeout(function () {
                try {
                    if (!frame.contentDocument || !frame.contentDocument.body || !frame.contentDocument.body.innerHTML) {
                        container.innerHTML = '<div class="no-play"><p>此视频无法在当前页面内播放</p><p style="font-size:12px;color:#666">原网站限制了嵌入访问</p><a href="' + esc(detailUrl) + '" target="_blank">前往原网页观看 -></a></div>';
                    }
                } catch (e) {
                    // cross-origin means the iframe loaded, but the page is not script-readable
                }
            }, 3000);
        } else {
            container.innerHTML = '<div class="no-play"><p>无可用播放链接</p></div>';
        }
    }

    function esc(s) {
        return s ? String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") : "";
    }

    function _cleanupPlayback() {
        if (hlsInstance) {
            hlsInstance.destroy();
            hlsInstance = null;
        }
        document.getElementById("playerContainer").innerHTML = "";
    }

    function destroy() {
        activeToken += 1;
        refreshPromise = null;
        playbackState = null;
        _cleanupPlayback();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.getElementById("playerClose").addEventListener("click", function () {
            document.getElementById("playerModal").classList.remove("open");
            destroy();
        });
        document.getElementById("playerModal").addEventListener("click", function (e) {
            if (e.target.id === "playerModal") {
                document.getElementById("playerModal").classList.remove("open");
                destroy();
            }
        });
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            document.getElementById("playerModal").classList.remove("open");
            destroy();
        }
    });

    return { open, destroy };
})();
