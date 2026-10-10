# 网盘助手（PanBox）

本目录是 `PanBox` 的 MoviePilot v2 后端源码及 Release 前端产物目录。面向用户的安装、配置和功能说明见
[网盘助手使用说明](../../docs/panbox.md)。

## 目录职责

```text
panbox/
├── __init__.py          # 插件入口、元数据及生命周期代理
├── requirements.txt     # Python 运行依赖
├── core/                # 领域模型、配置、平台适配和通用服务
├── drive/               # 网盘能力接口及提供方实现
├── handlers/            # 搜索、订阅、同步、通知和 API 编排
├── search/              # 搜索源客户端
├── utils/               # 文件解析、匹配、Magnet 和 STRM 工具
└── dist/assets/         # CI 构建后写入 Release ZIP 的 Vue 模块联邦产物
```

## 模块边界

- `core/` 定义插件自身业务模型与服务，不放具体网盘或搜索源实现。
- `drive/` 通过稳定能力协议接入网盘；调用方先检查能力，再获取对应服务。
- `search/` 只负责获取和标准化资源候选，不执行转存或文件处理。
- `handlers/` 组合领域服务并对接事件、API、通知和任务入口。
- `utils/` 仅保留无状态或低状态的通用辅助逻辑。

## 前端与发布

前端源码位于 [`frontend/panbox`](../../frontend/panbox)。
[`plugins-release.yml`](../../.github/workflows/plugins-release.yml) 在发布时生成并打入插件 ZIP。

插件版本必须同时更新：

- `__init__.py` 中的 `plugin_version`
- 仓库根目录 [`package.v2.json`](../../package.v2.json) 中的 `version`
- `package.v2.json` 中对应版本的 `history`

发布标签与资产命名遵循 MoviePilot 约定：

```text
PanBox_v<version>
panbox_v<version>.zip
```

## TG 频道搜索（tg_channel）

抓取 `https://t.me/s/<频道>?q=<关键词>` 公开预览页，仅支持公开频道。

配置键（`search/tg_channel/definition.py`）：

| 键 | 类型 | 说明 |
|:---|:---|:---|
| `tg_channel_search_enabled` | switch | 渠道总开关 |
| `tg_channels` | channel-list | 频道对象列表：`[{"id": "QukanMovie", "name": "115影视资源分享频道", "icon": "https://…"}]` |
| `tg_channel_result_limit` / `tg_channel_timeout` / `tg_channel_request_timeout` / `tg_channel_request_interval` | number | 候选上限、总超时、单请求超时、频道间隔 |

- **向后兼容**：`tg_channels` 旧值（纯字符串列表，如 `["QukanMovie"]`）在读取时统一归一为
  `{id, name, icon}` 对象；`name` 缺省回落为用户名，`icon` 缺省表示交给自动获取。
- **图标自动获取**：优先从同一次搜索响应里的频道信息块解析（`i.tgme_page_photo_image > img` /
  `img.tgme_page_photo_image` / `.tgme_header_link img`），无该块时补抓一次频道主页
  `https://t.me/<频道>`；结果按 7 天 TTL 缓存（`utils/cache.create_platform_ttl_cache`，
  命名空间 `tg_channel:info`），配置里手填的 `icon` 优先于自动结果，`clear_cache()` 会一并失效。
- **配置页自动填充**：`POST plugin/PanBox/search/source/info`（`{source, value, config}`）按渠道
  自描述钩子 `SearchSourceDefinition.resolve_source_info` 读取频道名称与头像，前端按钮一键回填。

候选字段（与 pansou、seedhub 对齐）与分组键：

```text
title / description / size(字节) / update_time / resource_type / url / tags / password
source_url(原始消息链接) / provider_data{channel, channel_name, channel_icon, channel_url,
message_id, message_url, password}
group_key="tg_channel:<频道用户名>" / group_title / group_icon / group_subtitle="@用户名"
/ group_order(频道在 tg_channels 配置里的下标，越小越靠前)
```

前端在候选携带 `group_key` 时按频道分组渲染（分组头为频道图标 + 名称 + 数量），
`provider_data.message_url` 提供「打开频道原始消息」，`update_time` 与 `password` 作为频道明细标签。

### 发布名（title）取值规则

`title` 取帖子里的**完整发布名**（含年份、规格、编码、音轨、字幕、体积等），而不是只留片名：

1. 定位命中媒体名的片名行，从片名位置起向后拼接「发布名头部块」——跳过纯表情/装饰行，
   遇到元数据标签行（`评分：`/`资源信息`/`• 体积：`）或链接行即止，最多再收集 4 个有效行；
2. 头部块为空时，回落到「命中媒体名的最长行」；
3. 再回落到整段正文中匹配片名所在的那一行；
4. 均未命中时取「最长有效行」（排除 `动漫｜`/`【更新】` 这类纯栏目行）。

清洗规则：去 emoji/LRM 等装饰符、剥独占栏目前缀（`动漫｜`、`【更新】`、`已更新：`）、
截断内联元数据（`评分：` 之后的段落）、去掉首尾装饰分隔符，但**保留成对括号**（`功夫女足 (2026)`）。
站内搜索结果页会把命中的关键词用高亮节点切开（`（2026）` → `（`/`2026`/`）` 三行），
拼接后会把括号内侧的多余空格收回。集数若已包含在发布名里则保留，不再重复追加。

### 分组顺序与折叠

- **顺序**：`group_order` = 频道在 `tg_channels` 配置里的下标；结果接口的候选会按
  `(seeders, size)` 全局排序，因此分组顺序由前端按 `group_order` 重排（缺失时回落首次出现顺序）。
  编辑器的上移/下移按钮直接交换 `tg_channels` 数组元素，保存即持久化该顺序。
- **折叠**：分组默认折叠，仅默认展开「第一个有资源的分组」；点击分组头（或回车/空格）展开/折叠。
- **网盘类型筛选**：`tg_channel` 标签页下隐藏网盘类型子 tab（胶囊按钮）且不做类型过滤
  （展示该频道全部候选）；其它渠道沿用原有子 tab 逻辑，行为不变。

