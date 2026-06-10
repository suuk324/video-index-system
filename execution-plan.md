# 执行计划：搭建项目基础框架

## 任务目标

搭建"个人网页视频聚合搜索播放器"的完整项目骨架，实现核心链路的第一轮端到端跑通：
添加视频源 → 扫描网页 → 提取视频信息 → 入库去重 → 搜索筛选 → 网页内播放 → 定时更新

## 涉及文件

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `requirements.txt` | 新增 | Python 依赖 |
| `backend/__init__.py` | 新增 | 包标记 |
| `backend/main.py` | 新增 | FastAPI 入口，挂载前端和 API |
| `backend/database.py` | 新增 | SQLite 初始化、表创建、CRUD 操作 |
| `backend/models.py` | 新增 | Pydantic 数据模型（请求/响应） |
| `backend/routers/__init__.py` | 新增 | 包标记 |
| `backend/routers/sources.py` | 新增 | 视频源管理 API（CRUD） |
| `backend/routers/videos.py` | 新增 | 视频列表/搜索/收藏 API |
| `backend/routers/scan.py` | 新增 | 手动触发扫描 API |
| `backend/adapters/__init__.py` | 新增 | 适配器基类 + 注册机制 |
| `backend/adapters/generic.py` | 新增 | 通用网页适配器（默认） |
| `backend/services/__init__.py` | 新增 | 包标记 |
| `backend/services/scanner.py` | 新增 | 扫描调度逻辑 |
| `backend/services/extractor.py` | 新增 | 网页信息提取逻辑 |
| `backend/scheduler.py` | 新增 | APScheduler 定时任务 |
| `frontend/index.html` | 新增 | 主页面（SPA 结构） |
| `frontend/css/style.css` | 新增 | 样式 |
| `frontend/js/app.js` | 新增 | 前端主逻辑 |
| `frontend/js/player.js` | 新增 | 播放器封装 |
| `start.py` | 新增 | 一键启动脚本 |

## 执行步骤

### 步骤 1：项目骨架 + 依赖
- 创建 requirements.txt（fastapi, uvicorn, httpx, beautifulsoup4, apscheduler）
- 创建所有目录和 `__init__.py`

### 步骤 2：数据库层
- database.py：SQLite 初始化、两张表（video_sources、videos）的创建和完整 CRUD
- 去重逻辑：基于 detail_url + source_id 联合唯一

### 步骤 3：数据模型
- models.py：VideoSource（创建/更新/响应）、Video（响应）、ScanResult、通用分页响应

### 步骤 4：适配器系统
- adapters/__init__.py：BaseAdapter 抽象基类 + AdapterRegistry 注册表
- adapters/generic.py：通用适配器，从 HTML 中提取 img/a/title 等通用结构

### 步骤 5：核心业务逻辑
- services/extractor.py：调用 httpx 抓取网页，用 BeautifulSoup 解析，调用适配器提取
- services/scanner.py：管理扫描任务，遍历启用的视频源，调用 extractor，结果入库

### 步骤 6：API 路由
- routers/sources.py：GET/POST/PUT/DELETE /api/sources
- routers/videos.py：GET /api/videos（搜索/筛选/分页）、PUT /api/videos/{id}/favorite、PUT /api/videos/{id}/watch
- routers/scan.py：POST /api/scan/{source_id}、POST /api/scan/all

### 步骤 7：定时任务 + 主入口
- scheduler.py：APScheduler 初始化，按各源的 refresh_interval 定时扫描
- main.py：FastAPI 应用，挂载 static 目录，注册路由，启动定时任务

### 步骤 8：前端页面
- index.html：HTML 骨架，包含视频源管理区、视频列表区、搜索栏、播放器模态框
- style.css：响应式卡片布局、播放器样式
- app.js：API 调用、列表渲染、搜索筛选、收藏/观看状态
- player.js：HTML5 video + hls.js 播放封装，处理 mp4/webm/m3u8/跳转

### 步骤 9：启动脚本
- start.py：检查依赖、初始化数据库、启动 uvicorn

### 步骤 10：验证
- 启动服务，访问前端页面
- 手动添加一个视频源
- 触发扫描，查看提取结果
- 测试搜索、筛选、播放
- 确认定时任务正常调度

## 风险评估

| 风险 | 影响 | 应对 |
|------|------|------|
| 通用适配器提取质量有限 | 部分网站提取不到有效信息 | 先实现通用能力，后续通过适配器扩展 |
| 前端 SPA 逻辑复杂 | 代码量大 | 按功能模块拆分 JS 文件 |
| httpx 抓取被反爬 | 部分网站无法扫描 | 设置合理的 User-Agent，后续可加代理 |

## 回滚方案

项目全新创建，无已有代码，不存在回滚问题。如需放弃，删除目录即可。
