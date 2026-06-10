# PROJECT_CONTEXT.md — 项目定位与边界

## 项目名称

个人网页视频聚合搜索播放器

## 项目定位

一个本地部署的**视频元数据聚合搜索引擎**。
核心理念：只收集视频的元信息（标题、封面、链接等），不下载视频本体。
播放时直接使用原网站公开的视频链接进行内嵌播放或跳转。

## 功能边界

### 包含（IN SCOPE）

| 模块 | 具体功能 |
|------|---------|
| 视频源管理 | 添加、删除、编辑视频源；设置名称、分类、网址、刷新间隔、启用/禁用 |
| 网页扫描 | 手动触发扫描 + 定时自动扫描 |
| 信息提取 | 从目标网页提取：标题、封面、简介、标签、关键词、发布时间、详情页链接、播放链接、来源网站 |
| 数据存储 | 本地数据库保存元数据，自动去重 |
| 搜索筛选 | 关键词搜索、分类筛选、标签筛选、来源筛选 |
| 视频播放 | 网页内播放 mp4、webm、m3u8 格式；无法提取直链时显示"需跳转原网页观看"并保留原链接 |
| 收藏与状态 | 收藏视频、记录观看状态 |
| 适配器系统 | 不同网站适配器扩展机制 |

### 不包含（OUT OF SCOPE）

| 项目 | 原因 |
|------|------|
| 下载视频文件 | 本项目只存链接，不存储任何视频本体 |
| 用户系统/多用户 | 个人工具，单用户使用 |
| 视频转码/处理 | 不涉及视频文件操作 |
| 社交功能 | 无需评论、分享、关注等 |
| 移动端 App | 仅 Web 端 |
| 需登录才能访问的网站 | 扫描仅限公开网页内容 |

### 预留能力（FUTURE）

- TVBox 订阅链接输出
- Miraplay 订阅链接输出
- M3U 订阅链接输出
- 更多网站适配器

## 技术边界

### 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端框架 | Python + FastAPI | 轻量、高性能、异步支持好 |
| 数据库 | SQLite | 本地单文件部署，无需额外数据库服务 |
| 前端 | 原生 HTML + CSS + JavaScript | 不引入前端构建工具，保持简单 |
| 爬虫引擎 | httpx + BeautifulSoup4 | 异步 HTTP + HTML 解析 |
| 定时任务 | APScheduler | Python 定时任务框架 |
| 视频播放 | hls.js + 原生 HTML5 video | 支持 m3u8 和 mp4/webm |

### 技术边界规则

1. **不引入重型框架** — 前端不用 React/Vue/Angular，后端不用 Django。
2. **不引入复杂依赖** — 每个依赖必须有明确用途，不堆砌库。
3. **数据库只用 SQLite** — 不引入 PostgreSQL/MySQL，个人工具不需要。
4. **不搞微服务** — 单体应用，前后端一体化部署。
5. **API 风格** — RESTful JSON API，前后端分离。
6. **代码风格** — Python 遵循 PEP 8，前端保持简洁可读。

## 数据模型概要

### 视频源（video_sources）
- id, name, category, url, refresh_interval, enabled, adapter_type, created_at, updated_at

### 视频信息（videos）
- id, source_id, title, cover_url, description, tags, keywords, publish_time, detail_url, play_url, play_type, source_name, is_favorite, watch_status, created_at, updated_at

## 项目目录结构（规划）

```
视频爬取/
├── AGENTS.md              # 工作总规则
├── PROJECT_CONTEXT.md     # 项目定位与边界
├── BUGFIX_RULES.md        # Bug 修复规则
├── CODE_REVIEW.md         # 代码自检规则
├── PLANS.md               # 执行计划模板
├── backend/
│   ├── main.py            # FastAPI 入口
│   ├── database.py        # 数据库初始化与操作
│   ├── models.py          # 数据模型
│   ├── routers/           # API 路由
│   ├── services/          # 业务逻辑
│   ├── adapters/          # 网站适配器
│   └── scheduler.py       # 定时任务
├── frontend/
│   ├── index.html         # 主页面
│   ├── css/               # 样式
│   └── js/                # 脚本
└── requirements.txt       # Python 依赖
```
