# Video Index System

一个本地部署的 **内容索引 / 元数据聚合 / 播放入口管理系统原型**。  
它会抓取公开网页中的标题、封面、标签、详情页与播放入口，并统一整理到本地数据库中，提供搜索、筛选、收藏、来源管理与导出能力。

> 说明：本项目只聚合公开页面的元数据，不下载视频文件本体。

## Two modes

### 1. Local system
完整的本地版本，包含：

- 来源管理
- 手动扫描 + 定时扫描
- 元数据提取与去重
- 搜索 / 分类 / 标签 / 来源筛选
- 收藏与观看状态
- 导出与订阅能力

### 2. Sanitized public demo
为了让作品集里可以稳定、安全地展示这个项目，仓库内额外提供了一个公开 demo：

- Live: `https://suuk324.github.io/video-index-system/`
- 路径：`demo/`
- 特点：使用中性样例数据
- 保留：界面设计、信息架构、筛选逻辑、source registry
- 移除：真实扫描、数据库更新、导出、敏感跳转能力

## Stack

- Frontend: HTML / CSS / JavaScript
- Backend: Python
- Data: SQLite
- Parsing: requests / BeautifulSoup / lxml

## Local run

```bash
pip install -r requirements.txt
python start.py
```

启动后在本地浏览器访问对应端口即可。

## Project structure

```txt
backend/    backend services and adapters
frontend/   original local UI
demo/       sanitized public showcase for GitHub Pages
start.py    local startup script
```

## Positioning

这个项目不是普通静态网页，而是把下面这些能力组合在一起的轻量系统原型：

- 内容索引
- 数据清洗
- 规则适配
- 搜索筛选
- 本地工具化工作流

重点不在“内容堆砌”，而在于把原始网页信息转译成一个可持续更新、可浏览、可扩展的系统界面。
