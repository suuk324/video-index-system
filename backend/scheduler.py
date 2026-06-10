"""定时扫描任务 — 基于 threading.Timer"""
import logging
import threading
from .database import get_sources
from .services.scanner import scan_source_async, get_status

logger = logging.getLogger(__name__)

_timers = {}
_running = False


def _scan_job(source_id):
    try:
        # 用同步方式直接跑（定时任务在自己的线程里）
        from .services.scanner import _do_scan
        from .database import get_source
        source = get_source(source_id)
        if source:
            _do_scan(source, max_pages=5000)
            logger.info(f"定时扫描完成: {source['name']}")
    except Exception as e:
        logger.error(f"定时扫描失败 source_id={source_id}: {e}")
    if _running and source_id in _timers:
        _schedule_one(source_id)


def _schedule_one(source_id):
    from .database import get_source
    source = get_source(source_id)
    if not source:
        return
    interval = max(source["refresh_interval"], 60)
    timer = threading.Timer(interval, _scan_job, args=[source_id])
    timer.daemon = True
    _timers[source_id] = timer
    timer.start()
    logger.info(f"已调度定时任务: {source['name']}，间隔 {interval}s")


def start_scheduler():
    global _running
    _running = True
    sources = get_sources(enabled_only=True)
    for source in sources:
        _schedule_one(source["id"])
    logger.info("定时任务调度器已启动")


def stop_scheduler():
    global _running
    _running = False
    for timer in _timers.values():
        timer.cancel()
    _timers.clear()
    logger.info("定时任务调度器已停止")


def reload_scheduler():
    stop_scheduler()
    start_scheduler()
