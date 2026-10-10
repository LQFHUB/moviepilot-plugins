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
```

前端在候选携带 `group_key` 时按频道分组渲染（分组头为频道图标 + 名称 + 数量），
`provider_data.message_url` 提供「打开频道原始消息」，`update_time` 与 `password` 作为频道明细标签。

