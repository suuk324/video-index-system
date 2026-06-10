# 执行计划：主页自动发现视频列表页

## 任务目标

当用户只提供主页 URL 时，系统自动从主页中发现视频列表页，再从列表页提取视频信息。

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| backend/adapters/generic.py | 修改 | 增加 discover_listing_urls 方法，从主页发现列表页 |
| backend/services/scanner.py | 修改 | 增加发现逻辑：先找列表页，再从列表页提取视频 |

## 执行步骤

### 步骤 1：generic.py 增加 discover_listing_urls
- 输入：主页 HTML + base_url
- 逻辑：扫描所有链接，按启发式规则筛选"看起来像视频列表页"的链接
- 启发式规则：
  - URL 路径包含关键词：movie/film/video/vod/list/play/drama/anime/series
  - 或链接文字包含：电影/电视剧/动漫/综艺/纪录片/分类
  - 排除：静态资源、登录、注册、关于、联系
- 输出：列表页 URL 列表

### 步骤 2：scanner.py 修改扫描逻辑
- 先获取用户提供的 URL
- 调用 discover_listing_urls 看能否找到列表页
- 如果找到了列表页，从每个列表页提取视频
- 如果没找到，回退到当前逻辑（直接从主页提取）
- 限制最多跟进 5 个列表页，避免过度抓取

### 步骤 3：验证
- 测试只有主页 URL 的场景
- 确认能发现列表页并提取视频
- 确认不破坏已有功能
