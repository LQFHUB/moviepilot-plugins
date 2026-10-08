# moviepilot-plugins（LQFHUB 个人插件仓库）

个人 MoviePilot 插件仓库，供自己的实例通过「插件市场源」安装与更新。
仓库地址：`https://github.com/LQFHUB/moviepilot-plugins`

## 目录约定

| 路径 | 用途 |
|:---|:---|
| `package.v3.json` + `plugins.v3/` | V3 代际插件（当前为空） |
| `package.v2.json` + `plugins.v2/` | V2 代际插件（V3 宿主会向后兼容扫描 `package.v2.json`） |
| `frontend/<插件>/` | 插件前端源码，仅供本地构建，不进运行时目录 |
| `icons/` | 插件图标（可选） |

## 当前内容

### PanBox（由「网盘订阅助手」改造）v1.6.6

- **来源**：改写自 `odomu/MoviePilot-Plugins` 的「网盘订阅助手」（原作者 **odomu**）。插件 ID/类名/目录已改为 `PanBox`，因此与市场里的第三方 `CloudSubscribe` **互不冲突、可并存**。
- **来源与许可**：源自 GPL-3.0 项目（原作者 **odomu**）；本仓库未附许可证文件，改造后再对外分发请自行补齐许可声明。
- **代际**：V2 布局（`plugins.v2/panbox/`），在 V3 宿主上经宿主的向后兼容路径加载（已实测可用）。
- **前端产物**：`plugins.v2/panbox/dist/assets/`（由 `frontend/cloudsubscribe` 构建后提交，因此索引里 `release: false`，不走 Release 分发）。
- **重新构建前端**：

  ```bash
  cd frontend/cloudsubscribe && npm install && npm run build
  ```

## 开发约定

见 `AGENTS.md`（含宿主版本、安装/更新流程、V3 与 V2 代际差异、以及本项目实测到的坑）。
