# PanBox · 网盘助手

自建 Telegram 公开频道资源搜索，并把网盘分享链接一键转存到自己的网盘。
MoviePilot V3 插件（`plugins.v3/panbox`），界面为 Vue 联邦组件 + 主界面侧栏整页。

## 主体信息

| 项 | 值 |
|:---|:---|
| 插件 ID / 类名 | `PanBox`（`plugins.v3/panbox/__init__.py`） |
| 运行目录 | `app/plugins/panbox/`（宿主安装时复制） |
| 名称 / 版本 | 网盘助手 / `0.1.0` |
| labels | 网盘,搜索,转存 |
| level / system_version | `1` / `>=3.1.0` |
| UI 模式 | `vue` 联邦，`get_render_mode() -> ("vue", "dist/assets")` |

## 功能范围（v0.2.0）

**侧栏入口（复用宿主菜单分组）**：

| 入口 | nav_key | section | 落地页 | 说明 |
|:---|:---|:---|:---|:---|
| 网盘资源 | `resource` | `discovery` | `AppPageResource` | 出现在 MP「探索」分组；豆瓣 / TMDB 双榜单 + 标题搜索 + 海报网格 + 详情（频道页签资源列表） |
| 网盘电影订阅 | `movie` | `subscribe` | `AppPageMovie` | 出现在 MP「订阅」分组；电影订阅的搜索与转存状态 |
| 网盘剧集订阅 | `tv` | `subscribe` | `AppPageTv` | 同上，剧集维度（含季号过滤） |
| 网盘助手 | `main` | `system` | `AppPage` | 管理页：搜索 / 历史 / 收藏 / 账号 |

**做**：

- 网盘资源浏览：复用宿主探索的**豆瓣与 TMDB** 两个数据源（榜单参数与探索页同源同参），海报网格展示；点开条目后按**频道页签**列出该条目在各 Telegram 频道中的网盘资源，可直接复制链接 / 收藏 / 转存。
- 资源搜索：抓取 `https://t.me/s/<频道>?q=<关键词>` 公开预览页，解析消息并识别网盘分享链接（115/夸克/阿里/天翼/123/百度/移动）。
- 频道管理：频道列表可配置，默认内置 5 个常用频道。
- 转存：首批支持 **115 网盘**（自研 HTTP 驱动）；转存前可先「预览分享内容」确认体积，避免误转超大资源。
- **网盘订阅（全自动）**：订阅某个影视条目后，定时服务按 `auto_sync_cron` 在频道中搜索 → 按网盘类型 / 季号 / 关键词 / 体积上下限筛选 → 选优转存 → 记录（同资源去重，不会重复转存）。
- 网盘账号管理：115 Cookie 录入与连通性校验、目标目录选择。
- 历史与收藏：搜索命中与转存结果自动入历史；收藏独立于历史。

**不做**（明确排除，避免回到"功能臃肿"）：

- 榜单自动订阅（豆瓣/猫眼/TMDB/Bangumi 等）
- 站点签到
- 整理/刮削/字幕/STRM 生成
- 通知与媒体库刷新
- AI Agent 工具
- 猴补丁改写宿主 `SubscribeChain` / `Scheduler`

## 用到的扩展点

`get_state` / `init_plugin` / `get_form` / `get_page` / `get_render_mode` / `get_sidebar_nav` / `get_api` / `get_service` / `stop_service`。
未使用 `get_command` / `get_dashboard` / `get_actions` / `get_agent_tools`。

## 配置项

配置由宿主保存（前端 `Config.vue` 发 `save`，宿主经 `PUT /api/v1/plugin/PanBox` 持久化）：

| 键 | 默认值 | 说明 |
|:---|:---|:---|
| `enabled` | `false` | 插件总开关 |
| `channels` | 5 个默认频道 | 频道列表，元素为 `{id, name}`，`id` 为 Telegram 频道用户名 |
| `search_limit` | `30` | 单频道结果上限 |
| `search_timeout` | `20` | 单次请求超时（秒） |
| `search_filter` | `true` | 是否按关键词对结果做后置过滤（Telegram 站内搜索为模糊匹配） |
| `search_base_url` | `https://t.me/s` | 频道预览页基址，可换镜像 |
| `p115_enabled` | `false` | 是否启用 115 转存 |
| `p115_cookie` | `""` | 115 网页版 Cookie（**凭证，不入库**） |
| `p115_transfer_cid` | `"0"` | 115 目标目录 ID（`0` 为根目录） |
| `p115_transfer_path` | `""` | 目标目录路径的展示备注 |
| `history_limit` | `500` | 历史上限 |
| `history_auto_record` | `true` | 搜索/转存是否自动写入历史 |
| `auto_sync_enabled` | `false` | 是否启用网盘订阅的定时自动搜索+转存 |
| `auto_sync_cron` | `0 */6 * * *` | 自动同步的 cron 表达式（宿主按 `CronTrigger.from_crontab` 解析） |
| `auto_sync_cloud_types` | `["p115"]` | 允许自动转存的网盘类型 |
| `auto_sync_prefer_keywords` | `4K,2160p,REMUX,高码` | 候选偏好关键词（命中越多越优先） |
| `auto_sync_exclude_keywords` | `预告,花絮,TS,枪版` | 候选排除关键词 |
| `auto_sync_min_size_gb` / `auto_sync_max_size_gb` | `0` / `0` | 体积上下限（0 表示不限制；体积取自 115 分享解析） |
| `auto_sync_max_per_run` | `3` | 单个订阅每次最多转存多少个资源 |

## 插件数据（宿主 KV）

| 数据键 | 内容 |
|:---|:---|
| `search_history` | 历史记录数组，元素含 `id` / `created_at` / `source`(`search`\|`transfer`) / `item` |
| `favorites` | 收藏数组，元素含 `id` / `created_at` / `note` / `item` |
| `subscriptions` | 订阅数组，元素含 `id`/`title`/`media_type`/`media_id`/`season`/`enabled`/过滤项/`last_*`/`transferred[]`/`seen[]` |

## 前端（Vue 联邦）

源码在 `frontend/`（Vite 5 + Vue 3 + Vuetify 3 + `@originjs/vite-plugin-federation`），构建产物落在 `dist/assets/`：

| 暴露模块 | 组件 | 宿主用途 |
|:---|:---|:---|
| `./Config` | `src/components/Config.vue` | 插件配置对话框，`emit save/close/switch`，配置由宿主保存 |
| `./Page` | `src/components/Page.vue` | 插件详情对话框（`nav_key != main` 时的兜底页面） |
| `./AppPage` | `src/components/AppPage.vue` | 主界面侧栏整页（`nav_key = main`），读取 `api`/`pluginId`/`navKey` |

要点：

- `remoteEntry.js` 必须位于 `dist/assets/` 根目录，且它引用的 js/css 与其同级（构建配置已固化，`npm run build` 末尾会自动校验）。
- 构建会剔除仅服务本地调试的产物（`index.html`、`src/main.js` 入口）与无引用的 `__federation_shared_*` 样式副本（联邦插件即使 `generate: false` 仍会产出约 250KB 的 Vuetify 样式重复件），见 `frontend/vite.config.js` 的 `pruneBundle` 插件。
- 前端始终通过宿主注入的 `api` 对象调用插件接口（`plugin/PanBox/...`），**不接触任何 Token**。
- 本地调试：`cd frontend && npm install && npm run dev`（调试台走 `index.html` + `src/main.js`，不进入产物）。

## 依赖

**无新增第三方依赖**。全部使用宿主已提供的运行时与接口：

- HTTP：`app.sdk.network.RequestUtils`
- HTML 解析：`beautifulsoup4`（MoviePilot 自带，`pyproject.toml` 中为 `beautifulsoup4~=4.15.0`）
- 其余仅用标准库

> 115 驱动为自研实现，**不使用** `p115client` 等第三方 SDK——避免向 MoviePilot 共享 Python 环境引入新依赖（该环境已有插件做过依赖钉版）。

## 对外副作用

- 出网请求：`https://t.me/s/*`（频道搜索）、`https://webapi.115.com/*`（115 转存）。
- 不写媒体库、不触发通知、不修改宿主配置。

## 来源与许可

- **独立实现**：参考同类插件的功能边界与接口事实，未复制其代码。
  - `CloudSubscribe`（网盘订阅助手，odomu / wklesss）为 **GPL-3.0**，本插件**不复制其代码**。
  - `CloudSaver`（`jiangrui1994/cloudsaver`，MIT）提供 TG 抓取思路与网盘链接正则的分类方式，同样未复制代码。
- 本仓库当前**未添加 LICENSE**（版权保留）。若后续复用上述任一项目的代码，需遵守其许可（GPL-3.0 具有传染性）。

## 开发与校验

```bash
# 语法编译
python -m compileall -q plugins.v3/panbox

# 纯逻辑单测（不联网、不依赖宿主）
python -m pytest plugins.v3/panbox/tests -q

# 前端构建（Vue 联邦，产物需落入 dist/assets）
cd plugins.v3/panbox/frontend && npm install && npm run build
```

已实测验证：真实频道搜索可命中并正确解析出网盘链接与提取码；`compileall` 通过；单测通过。

## 变更历史

| 版本 | 说明 |
|:---|:---|
| v0.2.0 | 侧栏改为复用宿主菜单分组（探索→网盘资源、订阅→电影/剧集）；新增豆瓣/TMDB 双榜单与海报网格、频道页签资源详情、订阅实体与定时自动搜索+转存引擎、中文季号识别 |
| v0.1.1 | 重设计设置面板（左侧分组导航、固定高度外壳、紧凑行式布局、字号 11~13px）；新增「转存前分享预览」只读接口 `/drive/preview`；修复本地调试台 Vuetify 组件未注册 |
| v0.1.0 | 首个版本：TG 频道资源搜索、115 转存、网盘账号管理、搜索历史与收藏、侧栏整页入口 |
