# PanBox 前端（Vue 联邦）

MoviePilot V3.1.1 联邦前端工程，向宿主暴露三个组件：

| 暴露名 | 源文件 | 宿主用途 |
|:--|:--|:--|
| `./Config` | `src/components/Config.vue` | 插件配置对话框（`initialConfig` / `save` / `layout` / `switch` / `close`） |
| `./Page` | `src/components/Page.vue` | 插件详情对话框（精简搜索 + 转存 + 收藏） |
| `./AppPage` | `src/components/AppPage.vue` | 主界面侧栏整页（`nav_key = main`，搜索/历史/收藏/账号四个页签） |

## 构建

```bash
npm install          # 依赖：vite 5.4.21 / @vitejs/plugin-vue 5.2.4 / @originjs/vite-plugin-federation 1.4.1 / vue 3.5.13 / vuetify 3.7.3
npm run build        # = vite build && node scripts/verify-dist.mjs
npm run dev          # 本地调试台（mock api，不参与联邦产物）
```

产物输出到 `../dist/assets`（即 `plugins.v3/panbox/dist/assets`），必须提交。
`npm run build` 末尾会自动校验：`remoteEntry.js` 存在、它引用的 js/css 全部存在且与其同目录（无子目录引用）。

## 与宿主的契约（已对照 V3.1.1 前端产物核实）

- 宿主按 `plugin/file/PanBox/dist/assets/remoteEntry.js` 取联邦入口，调用 `init(shareScope)` → `get('./Config'|'./Page'|'./AppPage')`；
  组件以 `api`、`pluginId`、`sourcePluginId`、`nativeSubscribe` 等 props 挂载，事件用 `onSave` / `onAction` / `onLayout` / `onSwitch` / `onClose`。
- 注入的 `api` 是 axios 实例（envelope 模式，**原样返回插件接口响应体**），并会自动把 `plugin/<源插件ID>` 改写为 `plugin/<实例ID>`、
  自动附加 Bearer Token。因此前端只写 `plugin/PanBox/xxx`，**绝不接触 Token**，也不自行拼 `/api/v1`。
- `Config` 不自行保存配置：只 `emit('save', 完整配置对象)`，由宿主 `PUT /api/v1/plugin/{id}`。
- `AppPage` 只读展示 + 调用插件 API；账号页输入的 Cookie 仅用于即时 `drive/check` 连通性测试，不写配置。

## 目录结构

```text
frontend/
├── index.html                 # 仅本地调试台入口（生产构建会被移除）
├── vite.config.js             # 联邦 + 产物平铺 + 产物清理插件（pruneBundle）
├── scripts/verify-dist.mjs    # 产物完整性校验（构建后自动执行）
└── src/
    ├── main.js                # 仅开发环境引导（生产构建摇树移除）
    ├── dev/                   # 本地调试台（mock api）
    ├── utils/                 # api 客户端、网盘标签/时间格式化、剪贴板
    ├── composables/           # 提示条、资源转存/收藏动作
    └── components/
        ├── Config.vue  Page.vue  AppPage.vue        # 三个联邦暴露组件
        ├── common/  ResourceCard.vue  FolderPicker.vue
        └── panels/  SearchPanel.vue  HistoryPanel.vue  FavoritesPanel.vue  AccountPanel.vue
```

## 构建配置的两个注意点（实测踩坑记录）

1. `build.assetsDir` 必须留空而不是 `.`：联邦插件用 `${assetsDir}/${filename}` 生成 remoteEntry 文件名，
   取值为 `.` 时会得到 `./remoteEntry.js`，Rollup 直接报错。产物平铺由 `rollupOptions.output` 的文件名模板保证。
2. 宿主只按 `remoteEntry.js` 同级相对路径加载资源，因此构建末尾用 `pruneBundle()` 插件删除 Vite 的 HTML 入口产物，
   以及联邦插件即使配置 `generate: false` 仍会为 `vuetify/styles` 产出的约 250 kB 样式副本
   （无任何文件引用；宿主自身样式包已实测包含完整 Vuetify 样式）。
