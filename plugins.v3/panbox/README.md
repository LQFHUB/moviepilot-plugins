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

## 功能范围（v0.1.0）

**做**：

- 资源搜索：抓取 `https://t.me/s/<频道>?q=<关键词>` 公开预览页，解析消息并识别网盘分享链接（115/夸克/阿里/天翼/123/百度/移动）。
- 频道管理：频道列表可配置，默认内置 5 个常用频道。
- 转存：首批支持 **115 网盘**（自研 HTTP 驱动）。
- 网盘账号管理：115 Cookie 录入与连通性校验、目标目录选择。
- 搜索历史与收藏：搜索命中可自动入历史；收藏独立于历史。
- 侧栏整页入口：`get_sidebar_nav()` 提供 `nav_key = main`。

**不做**（明确排除，避免回到"功能臃肿"）：

- 榜单自动订阅（豆瓣/猫眼/TMDB/Bangumi 等）
- 站点签到
- 整理/刮削/字幕/STRM 生成
- 通知与媒体库刷新
- AI Agent 工具
- 猴补丁改写宿主 `SubscribeChain` / `Scheduler`

## 用到的扩展点

`get_state` / `init_plugin` / `get_form` / `get_page` / `get_render_mode` / `get_sidebar_nav` / `get_api` / `stop_service`。
未使用 `get_service` / `get_command` / `get_dashboard` / `get_actions` / `get_agent_tools`（内核无常驻服务）。

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
| `search_proxy` | `""` | 可选代理，形如 `http://127.0.0.1:7890` |
| `p115_enabled` | `false` | 是否启用 115 转存 |
| `p115_cookie` | `""` | 115 网页版 Cookie（**凭证，不入库**） |
| `p115_transfer_cid` | `"0"` | 115 目标目录 ID（`0` 为根目录） |
| `p115_transfer_path` | `""` | 目标目录路径的展示备注 |
| `history_limit` | `500` | 历史上限 |
| `history_auto_record` | `true` | 搜索/转存是否自动写入历史 |

## 插件数据（宿主 KV）

| 数据键 | 内容 |
|:---|:---|
| `search_history` | 历史记录数组，元素含 `id` / `created_at` / `source`(`search`\|`transfer`) / `item` |
| `favorites` | 收藏数组，元素含 `id` / `created_at` / `note` / `item` |

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
| v0.1.0 | 首个版本：TG 频道资源搜索、115 转存、网盘账号管理、搜索历史与收藏、侧栏整页入口 |
