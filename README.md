# Video Index System

一个本地部署的**公开视频元数据聚合与播放管理系统**。  
它会抓取公开网页中的视频标题、封面、标签、详情页和播放入口，统一存进本地数据库，提供搜索、筛选、收藏、源管理和订阅导出能力。

> 说明：本项目只聚合**公开页面元数据**，不下载视频文件本体。

## Stack

- Frontend: HTML / CSS / JavaScript
- Backend: Python / FastAPI
- Data: SQLite
- Scheduler: APScheduler
- Parsing: httpx / BeautifulSoup

## Core Features

- 多视频源管理
- 手动扫描 + 定时扫描
- 视频元数据提取与去重
- 搜索 / 分类 / 标签 / 来源筛选
- 页面内播放与跳转原站播放
- 收藏与观看状态管理
- 订阅导出（TVBox / M3U / Miraplay）
- 适配器机制，方便扩展不同站点规则

## Local Run

```bash
pip install -r requirements.txt
python start.py
```

默认启动后可在本地浏览器访问对应端口查看。

## Project Structure

```txt
backend/    FastAPI, database, routers, services, adapters
frontend/   HTML, CSS, JS, player
start.py    local startup script
```

## Positioning

这个项目不是普通静态网页，而是一个把：

- 内容索引
- 数据清洗
- 规则适配
- 搜索筛选
- 前后端联动

组合在一起的轻量系统型产品原型。
