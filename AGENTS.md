# AGENTS.md · MoviePilot 插件开发约定

本目录用于开发 MoviePilot 插件。以下约定基于 **MoviePilot V3.1.1 源码实测**（非记忆推测）；标「未验证」的条目必须先确认再依赖。

---

## 1. 目标环境（已核实）

| 项 | 值 |
|:---|:---|
| 运行实例 | `http://192.168.31.200:3000`（NAS Docker 容器 `moviepilot-v3`） |
| 镜像 / 版本 | `jxxghp/moviepilot-v3:3.1.1`，后端 3.1.1 / 前端 3.1.2（2026-10-07 由 v2 迁移） |
| 宿主角色标识 | `VERSION_FLAG = "v3"`（`app/runtime/config.py:1176`） |
| 本目录在 NAS 的真实路径 | `/volume1/share/devInstall/project/deepseek/moviepilot`（NFS 挂载 `192.168.31.200:/volume1/share`） |
| API 凭证 | 知识库 `autu.md` 的「MoviePilot API」节，**不入库、不写进本目录任何文件** |

**代际结论**：宿主是 V3 → 一律使用 V3 布局（`package.v3.json` + `plugins.v3/`），不要生成 `plugins.v2/` 或 v1 的 `plugins/`。

## 2. 目录布局

```text
.
├── package.v3.json                     # 插件索引，键 = 插件类名
├── plugins.v3/
│   └── <plugin_id_lower>/
│       ├── __init__.py                 # 必需：插件实现
│       ├── pyproject.toml              # 仅当需要额外依赖
│       └── dist/assets/                # 仅 Vue 联邦插件：remoteEntry.js 及其引用资源
└── icons/                              # 可选：放 icon 字段引用的图标（仓库惯例，宿主不解析）
```

- 索引文件名 `package.{version}.json`、插件根目录 `plugins.{version}`（`app/adapters/external/plugin/client.py:495-524`）。
- 插件 ID = 类名（如 `MyNotifier`）；目录名 = 类名小写（`mynotifier`）；安装后运行目录为 `app/plugins/<id_lower>/`（`app/runtime/extensions/plugin/loader.py:194`）。
- **只改 `plugins.v3/` 下的源码**，不要直接写运行目录 `app/plugins/`。
- **一插件一目录**：每个插件独立占用 `plugins.v3/<plugin_id_lower>/`，插件之间不共享代码文件，不要把新插件塞进别的插件目录。新增插件 = 新建目录 + 在 `package.v3.json` 追加同名条目。

## 3. 元数据 `package.v3.json`

V3.1.1 的插件展示/升级信息**以索引条目为权威**（`app/runtime/extensions/plugin/metadata.py:84-102`）：

```json
{
  "MyNotifier": {
    "name": "通知示例",
    "description": "按配置发送示例通知。",
    "labels": "消息通知",
    "version": "1.0.0",
    "icon": "mynotifier.png",
    "author": "<作者>",
    "level": 1,
    "system_version": ">=3.1.0",
    "history": { "v1.0.0": "初始版本" }
  }
}
```

- 键必须等于插件类名；`version` 与类属性 `plugin_version` 保持一致（后者用于已安装/线上版本比对）。
- `system_version` 为 PEP 440 区间，与宿主版本比对（`client.py:378-408`）。
- 排除某代：条目加 `"v3": false`；`release: true` 表示走 GitHub Release 分发。
- `level` 是**要求的站点认证等级**（`app/runtime/extensions/plugin/access.py:23-60`）：宿主等级 ≥ `level` 才可见；普通插件填 `1`，`99` 表示需 `PLUGIN_<ID>_PRIVATE_KEY` 的特殊密钥插件。
- `icon` 仅是文件名，V3.1.1 宿主无图标解析/分发接口（前端按插件仓库 `icons/` 惯例取图），本地仓库的图标不保证生效。
- ⚠️ **与旧模板的差异**：V3.1.1 **不再**从类上读取 `plugin_config_prefix`（宿主自动生成 `<instance_id_lower>_`）、`auth_level`、`plugin_label`。旧示例里的这三个类属性不要照抄。

## 4. 插件骨架

抽象方法必须全部实现：`init_plugin` / `get_state` / `get_api` / `get_form` / `get_page` / `stop_service`（`app/sdk/plugin/base.py`）。

```python
from typing import Any, Dict, List, Optional, Tuple

from app.sdk.plugin import _PluginBase  # 稳定公开入口；app.plugins 为兼容惰性入口


class MyNotifier(_PluginBase):
    """通知示例插件。"""

    plugin_name = "通知示例"
    plugin_desc = "按配置发送示例通知。"
    plugin_icon = "mynotifier.png"
    plugin_version = "1.0.0"
    plugin_order = 100

    _enabled = False

    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """根据插件配置初始化运行状态。"""
        self.stop_service()
        self._enabled = bool((config or {}).get("enabled"))

    def get_state(self) -> bool:
        """获取插件启用状态。"""
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """返回插件 API 列表。"""
        return []

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """返回 Vuetify 配置表单与默认配置。"""
        return [{"component": "VForm", "content": []}], {"enabled": False}

    def get_page(self) -> Optional[List[dict]]:
        """返回插件详情页面。"""
        return None

    def stop_service(self) -> None:
        """停止插件后台服务并释放资源。"""
        return None
```

按需实现的扩展点：`get_command`、`get_service`、`get_dashboard`/`get_dashboard_meta`、`get_actions`、`get_agent_tools`、`get_render_mode`、`get_sidebar_nav`；数据与配置用 `update_config`、`save_data`/`get_data`/`del_data`。
一次性/延迟任务用 `app.sdk.scheduler.add_plugin_once_job(...)`，并在 `stop_service()` 里 `remove_plugin_once_job()`。

## 5. UI 两种模式（必须先问，不可默认）

| 模式 | 实现 | 产物 |
|:---|:---|:---|
| Vuetify JSON（默认） | `get_form`/`get_page`/`get_dashboard` 返回 JSON 组件树 | 纯后端，无前端构建 |
| Vue 联邦 | `get_render_mode()` 返回 `("vue", "dist/assets")`，Vite federation 暴露 `Page`/`Config`/`Dashboard`/`AppPage` | 插件目录内 `dist/assets/remoteEntry.js` |

- 需要侧栏整页时另实现 `get_sidebar_nav()`（仅对启用的 vue 插件聚合）。
- `get_render_mode` 的源码 docstring 写作 `dist/asserts`（拼写笔误），实际以声明值为准；构建入口固定为 `remoteEntry.js`。
- 前端调用插件 API 用 `auth: "bear"` 并经前端注入的 `api` 对象，不要把 Token 传给浏览器组件。

## 6. 硬性约定

1. **中文 docstring**：新增的类、方法、函数（含私有）必须写中文 docstring。
2. **复用宿主能力**：`app.sdk.*` 是宿主声明给插件的稳定接口（`app/sdk/__init__.py`）。HTTP 用 `app.sdk.network`（`RequestUtils`/`AsyncRequestUtils`），通用工具用 `app.sdk.utilities`，日志用 `app.sdk.logging`；不要裸用 `requests` 或自建调度器。
3. **凭证零入库**：不提交 Token/密码/API Key，代码中只放配置项或 `<PLACEHOLDER>`；需要时从知识库 `autu.md` 读取。
4. **生产实例只读优先**：`192.168.31.200:3000` 是运行中的服务。安装、重载、改系统配置、重启前必须先说明影响并征得同意；不要擅自停服或覆盖宿主配置。
5. **最小改动**：只改必要部分，风格与仓库内既有插件一致。

## 7. 校验（提交前）

```bash
python -m compileall -q plugins.v3/<plugin_id_lower>
```

自检清单：

- [ ] 类名 == 目录名（小写）== `package.v3.json` 键，且 `version` 与 `plugin_version` 同步
- [ ] 6 个抽象方法齐全，所有新增函数/方法有中文 docstring
- [ ] Vue 联邦插件：`dist/assets/remoteEntry.js` 存在且引用资源齐全
- [ ] 无凭证、无真实网络依赖的测试

## 8. Git 与 GitHub（本目录即插件仓库）

- **仓库形态**：本目录就是插件仓库根，用 Git 管理并推送到 GitHub：`https://github.com/LQFHUB/moviepilot-plugins`（public，`main` 分支；Token 见知识库 `autu.md` 的「GitHub」节，**不得写入仓库或 remote URL**）。
- **一插件一目录**：每开发一个新插件，就在 `plugins.v3/<plugin_id_lower>/` 新建独立目录，并在 `package.v3.json` 追加同名条目；插件之间不共享代码文件，也不要把新插件塞进别的插件目录。
- **必须提交的内容**：市场安装只读取 `<repo>/package.v3.json` 与 `<repo>/plugins.v3/<id_lower>/`（`client.py:490-536`）；Vue 联邦插件的 `dist/assets/` 构建产物也要提交——宿主不会替插件构建前端。
- **提交前**：完成第 7 节自检；`.gitignore` 至少覆盖 `__pycache__/`、`*.py[cod]`、`.venv/`，但**不要**忽略 `dist/assets/`。

## 9. 安装 / 联调

主路线（已定）：**GitHub 仓库 + 插件市场源**

1. 本目录推送到 GitHub 插件仓库 `LQFHUB/moviepilot-plugins`（已就绪，`main` 分支）。
2. 在 MoviePilot 系统设置 `PLUGIN_MARKET` 追加仓库地址，多个地址用 `,` 分隔且**地址以 `/` 结尾**（`app/runtime/config.py:693-694`），即追加 `https://github.com/LQFHUB/moviepilot-plugins/`。
3. 在插件市场刷新，即可看到 `package.v3.json` 中的插件；安装会把源码复制到运行目录 `app/plugins/<id_lower>/`，改 `version` 后即为一次更新。
4. ⚠️ 第 2 步会改动**运行中实例**的系统设置，执行前先说明并征得同意。

**实例实测到的接口事实（2026-10-08 安装 PanBox 时验证）**：

| 操作 | 方法与路径 | 备注 |
|:---|:---|:---|
| 读系统设置 | `GET /api/v1/system/settings?setting_key=<KEY>` | 返回 `data.settings[0].value` 与 `revision`；**不是** `/api/v1/settings/...`（那是 404） |
| 改系统设置 | `POST /api/v1/system/settings` | body：`{setting_key, value, operation:"replace", expected_revision}` |
| 刷新市场清单 | `GET /api/v1/plugin/?force=true&query=<ID>` | 重建市场清单；83 个仓库约 33 秒 |
| 安装插件 | **`GET`** `/api/v1/plugin/install/{plugin_id}?force=true` | ⚠️ 是 **GET** 不是 POST（用 POST 会得到 405）；约 37 秒 |
| 读/写插件配置 | `GET` / **`PUT`** `/api/v1/plugin/{plugin_id}` | PUT body 即插件配置 dict（需 superuser） |
| 取插件静态文件 | `GET /api/v1/plugin/file/{plugin_id_lower}/{path}` | 需 resource token（登录 Cookie）；无 token 返回 401 |

⚠️ **改仓库后必须先刷新市场再安装**：`install` 读取的是**冻结的市场清单**（`gateway.py:111` 的 `__inventory(False)`），不是安装时现拉。只 `force=true` 而不刷新市场，会装到**旧载荷**——实测出现过「新 chunk 文件已就位、`remoteEntry.js` 仍是旧版」的不一致状态。正确顺序：`push` → 刷新市场（`force=true`）→ 安装。
⚠️ **安装后要校验变更生效**：对比实例返回的 `remoteEntry.js` 与本地构建产物的 sha256（见 README「前端」）。

**当前实例上的改动（如需回滚）**：`PLUGIN_MARKET` 已追加 `https://github.com/LQFHUB/moviepilot-plugins`（原 82 条 → 83 条）；原值与 revision 备份在 `/tmp/mp_settings_backup_20261008.json`（`/tmp` 易失，需长期保留请另存）。回滚即用该文件里的 `value` 做一次 `replace`。

备选路线：本地插件源 —— 系统设置 `PLUGIN_LOCAL_REPO_PATHS`（`app/runtime/config.py:705`，逗号分隔，相对路径相对 `ROOT_PATH`）配合 `PLUGIN_AUTO_RELOAD` 热同步。
- ⚠️ **未验证**：`moviepilot-v3` 容器是否挂载 `/volume1/share` 及容器内对应路径；NAS 无 SSH 权限（`root@192.168.31.200` 公钥被拒），走此路线前需在 NAS 侧确认。

## 10. 插件登记表（本仓库开发的插件）

**本表只登记本仓库将要/正在开发的插件**，不登记运行实例上已安装的第三方插件。新增、改名、升级、下线插件时，必须同步更新本表与 `package.v3.json`。

| 插件 ID | 目录 | 名称 | 版本 | UI 模式 | 状态 | 用途与边界 |
|:---|:---|:---|:---|:---|:---|:---|
| `PanBox` | `plugins.v3/panbox` | 网盘助手 | 0.1.0 | vue 联邦 | 联调中 | 自建 TG 频道资源搜索 + 转存到网盘 + 网盘账号管理 + 搜索历史/收藏 + 侧栏整页入口；**不做**榜单自动订阅/站点签到/整理刮削STRM/通知与媒体库刷新/Agent 工具 |

`PanBox` 详情（完整信息见 `plugins.v3/panbox/README.md`）：
- **参考来源**：`CloudSubscribe`（网盘订阅助手，**两版均为 GPL-3.0**，仅参考功能边界与接口事实，**禁止复制其代码**）、`CloudSaver`（`jiangrui1994/cloudsaver`，MIT，参考 TG 抓取思路与网盘链接分类；其开源版为 V0.2.5、线上镜像 0.9.1，能力差异大）。
- **本仓库许可证：暂不加**（版权保留）。若日后复用 GPL-3.0 项目代码，PanBox 须整体以 GPL-3.0 发布。
- **搜索实现**：自建抓取 `https://t.me/s/<频道>?q=<关键词>` 公开预览页，用宿主自带的 beautifulsoup4 解析；频道列表由插件配置（默认 5 个）。已实测：真实频道能命中并解析出网盘链接与提取码。Telegram 站内搜索为模糊匹配，需按 `search_filter` 做后置过滤。
- **转存实现**：115 网盘，自研 HTTP 驱动（`drive/p115.py`，走 `https://webapi.115.com` 的 `share/snap`、`files`、`share/receive`）。**不引入 `p115client`**：宿主无该库，且共享环境已有插件做过依赖钉版，新增依赖有冲突风险（详见 README「依赖」）。
- **持久化**：历史与收藏走宿主 `save_data`/`get_data`（键 `search_history`、`favorites`），未自建数据库。
- **校验命令**：`python -m compileall -q plugins.v3/panbox`；`python -m pytest plugins.v3/panbox/tests -q`（17 项测试，已通过）；`cd plugins.v3/panbox/frontend && npm run build`（构建末尾自动校验 `dist/assets` 产物完整性）。
- **实例联调结果（2026-10-08，已在 `192.168.31.200:3000` 安装并启用）**：
  - ✅ 已安装（v0.1.0，`has_page=True`、`runtime_compatible=True`），已启用；宿主侧栏 `sidebar_nav` 唯一入口即 PanBox（`nav_key=main`、`section=system`、`permission=manage`）。
  - ✅ 联邦组件已注册：`/plugin/file/panbox/dist/assets/remoteEntry.js?v=0.1.0`，与本地构建产物 sha256 **一致**；entry 引用的 8 个 js/css 由实例返回 **全部 200**。
  - ✅ 浏览器实测（真实宿主前端 v3.1.2，admin 登录）：侧栏「网盘助手」→ `#/plugin-app/PanBox/main` 正常渲染；四个页签（搜索/历史/收藏/账号）均正常；插件卡片详情对话框（`Page.vue`）正常；插件市场列表卡片显示名称/版本/描述/作者。
  - ✅ UI 内真实搜索成功：关键词「流浪地球」跨 5 频道返回 **19 条 / 9261ms**，卡片正确显示频道、时间、网盘类型、提取码、复制/收藏/原消息链接。
  - ✅ 失败路径有可读提示：点击「转存到115」弹出 snackbar「115 网盘未启用（请在插件配置中开启）」。
  - ✅ API 层：`meta`/`search`/`history`(自动记录 19 条)/`favorites`(增·去重·删)/`drive.*` 失败路径 全部符合预期；零凭证泄露（提交内容与前端代码均未含 Token）。
- **尚未验证（勿当作已可用）**：
  1. **115 转存链路仍未经真实 Cookie 验证**——需要用户先在插件设置页填入 115 Cookie 并开启 115，才能实测 `share/snap`、`files`、`share/receive` 全链路；
  2. **配置对话框（`Config.vue`）未在宿主 UI 中打开验证**——其 expose 已注册、资源可取（200），且已由协议级冒烟测试覆盖，但宿主「设置 → 插件 → 网盘助手 → 设置」的真实打开路径未跑通（虚拟列表内按钮难以稳定点击）。
- **已知设计取舍**：Telegram 站内搜索是模糊匹配，命中率取决于频道与关键词，故提供 `search_filter` 后置过滤开关；历史记录按「来源 + 资源」去重，避免重复搜索堆积。

状态取值：`规划中` / `开发中` / `联调中` / `已发布` / `已下线`。

### 每个插件的「相关信息」记录要求

- **主体信息**（与 `package.v3.json` 条目保持一致）：插件 ID = 类名、目录名（小写）、名称、描述、labels、author、level、system_version、当前版本与 `history`。
- **UI 模式**：`vuetify` JSON 或 `vue` 联邦；联邦插件记录暴露的组件名与 `dist/assets` 路径。
- **用到的扩展点**：`get_api` / `get_service` / `get_command` / `get_actions` / `get_agent_tools` / `get_sidebar_nav` / `get_dashboard`（只列实际用到的）。
- **配置与数据**：配置项键名；`save_data`/`get_data` 使用的 key（配置前缀由宿主生成为 `<instance_id_lower>_`，不需插件声明）。
- **额外依赖**：`pyproject.toml` 新增依赖及其理由。
- **对外副作用**：访问的网络目标、通知渠道、是否写媒体库/下载器。
- **来源与许可**：自研，或改造自第三方（记录原插件 ID、原仓库、许可证）。
- **变更历史**：版本 → 说明，与索引 `history` 同步。

详情写在各插件目录内的 `README.md`，本表只保留一行总览，避免本文件膨胀。

## 11. 事实来源

- 本地 MoviePilot V3.1.1 源码副本：`/tmp/mp-v3-src`（解包所得，非 git 仓库；**`/tmp` 可能被清理**，引用前先确认存在）。
- 知识库《🏠 日常/家庭基础设施.md》《autu.md》。
- 相关技能：`/tmp/mp-v3-src/skills/create-moviepilot-plugin/SKILL.md`（V3/V2 通用流程，个别模板字段已过时，以本文第 3 节为准）。

> 另：全局约定见 `~/.dsh/AGENTS.md`（简体中文回复、诚实原则、最小改动、破坏性操作前先说明）。
