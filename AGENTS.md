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

- **仓库形态**：本目录就是插件仓库根，用 Git 管理并推送到 GitHub（账号 `LQFHUB`；Token 见知识库 `autu.md` 的「GitHub」节，**不得写入仓库**）。
- **一插件一目录**：每开发一个新插件，就在 `plugins.v3/<plugin_id_lower>/` 新建独立目录，并在 `package.v3.json` 追加同名条目；插件之间不共享代码文件，也不要把新插件塞进别的插件目录。
- **必须提交的内容**：市场安装只读取 `<repo>/package.v3.json` 与 `<repo>/plugins.v3/<id_lower>/`（`client.py:490-536`）；Vue 联邦插件的 `dist/assets/` 构建产物也要提交——宿主不会替插件构建前端。
- **提交前**：完成第 7 节自检；`.gitignore` 至少覆盖 `__pycache__/`、`*.py[cod]`、`.venv/`，但**不要**忽略 `dist/assets/`。

## 9. 安装 / 联调

主路线（已定）：**GitHub 仓库 + 插件市场源**

1. 本目录推送到 GitHub 插件仓库。
2. 在 MoviePilot 系统设置 `PLUGIN_MARKET` 追加仓库地址，多个地址用 `,` 分隔且**地址以 `/` 结尾**（`app/runtime/config.py:693-694`），例如 `https://github.com/LQFHUB/<仓库>/`。
3. 在插件市场刷新，即可看到 `package.v3.json` 中的插件；安装会把源码复制到运行目录 `app/plugins/<id_lower>/`，改 `version` 后即为一次更新。
4. ⚠️ 第 2 步会改动**运行中实例**的系统设置，执行前先说明并征得同意。

备选路线：本地插件源 —— 系统设置 `PLUGIN_LOCAL_REPO_PATHS`（`app/runtime/config.py:705`，逗号分隔，相对路径相对 `ROOT_PATH`）配合 `PLUGIN_AUTO_RELOAD` 热同步。
- ⚠️ **未验证**：`moviepilot-v3` 容器是否挂载 `/volume1/share` 及容器内对应路径；NAS 无 SSH 权限（`root@192.168.31.200` 公钥被拒），走此路线前需在 NAS 侧确认。

## 10. 事实来源

- 本地 MoviePilot V3.1.1 源码副本：`/tmp/mp-v3-src`（解包所得，非 git 仓库；**`/tmp` 可能被清理**，引用前先确认存在）。
- 知识库《🏠 日常/家庭基础设施.md》《autu.md》。
- 相关技能：`/tmp/mp-v3-src/skills/create-moviepilot-plugin/SKILL.md`（V3/V2 通用流程，个别模板字段已过时，以本文第 3 节为准）。

> 另：全局约定见 `~/.dsh/AGENTS.md`（简体中文回复、诚实原则、最小改动、破坏性操作前先说明）。
