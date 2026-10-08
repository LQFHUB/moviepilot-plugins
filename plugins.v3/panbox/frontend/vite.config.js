import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

/**
 * 清理产物：只保留宿主真正需要的联邦资源。
 *
 * `order: 'post'` 保证在 Vite 的 HTML 插件与联邦插件处理完之后执行。做两件事：
 * 1. 删除仅服务于本地开发的入口产物：Vite 构建以 `index.html` 为 Rollup 输入，
 *    会产出 `index.html` 与对应 JS 块（facadeModuleId 指向 index.html）；
 * 2. 删除没有任何文件引用的 `__federation_shared_*` 资源：联邦插件即使配置了
 *    `generate: false`，仍会为 `vuetify/styles` 额外产出一份约 250 kB 的样式副本，
 *    而宿主自身的样式包已实测包含完整 Vuetify 样式（`.v-btn` 等选择器 400+ 处），
 *    该副本没有任何引用方，属于纯重复内容。
 */
function pruneBundle() {
  return {
    name: 'panbox:prune-bundle',
    generateBundle: {
      order: 'post',
      handler(_options, bundle) {
        // 1. 本地开发入口
        for (const name of Object.keys(bundle)) {
          const item = bundle[name]
          const isHtml = name.endsWith('.html')
          const isDevEntry =
            item.type === 'chunk' &&
            typeof item.facadeModuleId === 'string' &&
            item.facadeModuleId.endsWith('/index.html')
          if (isHtml || isDevEntry) {
            delete bundle[name]
          }
        }

        // 2. 无引用方的共享样式副本
        const remaining = Object.entries(bundle)
        for (const [name, item] of Object.entries(bundle)) {
          if (!name.startsWith('__federation_shared_')) continue
          const basename = name.split('/').pop()
          const referenced = remaining.some(([otherName, other]) => {
            if (otherName === name || other.type !== 'chunk' || typeof other.code !== 'string') return false
            return other.code.includes(name) || other.code.includes(basename)
          })
          if (!referenced && item.type === 'asset') {
            delete bundle[name]
          }
        }
      },
    },
  }
}

/**
 * PanBox Vue 联邦前端构建配置。
 *
 * 宿主（MoviePilot V3.1.1）按 `plugin/file/PanBox/dist/assets/remoteEntry.js` 取联邦入口，
 * 并调用 `init(shareScope)` + `get('./Config' | './Page' | './AppPage')`，因此：
 * - 产物必须平铺在 `dist/assets/` 根目录（`outDir` 指向插件目录下的 dist/assets）；
 * - `remoteEntry.js` 内部使用相对自身 URL 的动态 import，引用到的 js/css 必须与它同级；
 * - `target: 'esnext'`：联邦运行时与共享依赖解析依赖顶层 await。
 */
export default defineConfig({
  plugins: [
    vue(),
    federation({
      // 联邦容器名，需与插件类名一致，便于宿主排查
      name: 'PanBox',
      filename: 'remoteEntry.js',
      exposes: {
        './Config': './src/components/Config.vue',
        './Page': './src/components/Page.vue',
        './AppPage': './src/components/AppPage.vue',
        // 宿主按 `./AppPage{PascalCase(nav_key)}` 解析非 main 的侧栏页
        './AppPageResource': './src/components/AppPageResource.vue',
        './AppPageMovie': './src/components/AppPageMovie.vue',
        './AppPageTv': './src/components/AppPageTv.vue',
      },
      shared: {
        // 由宿主提供运行时，插件侧不重复打包（generate: false）
        vue: { requiredVersion: false, generate: false },
        vuetify: { requiredVersion: false, generate: false, singleton: true },
        'vuetify/styles': { requiredVersion: false, generate: false, singleton: true },
      },
      format: 'esm',
    }),
    pruneBundle(),
  ],
  build: {
    target: 'esnext',
    cssCodeSplit: true,
    // 相对 frontend/ 目录：产物直接落到插件目录的 dist/assets
    outDir: '../dist/assets',
    // 注意：这里必须留空而不是 '.'。联邦插件用 `${assetsDir}/${filename}` 生成 remoteEntry 的
    // 文件名，取值为 '.' 时会得到 './remoteEntry.js'，Rollup 会直接报错（不允许相对路径文件名）。
    // 产物平铺由下面 rollupOptions.output 的文件名模板（不带目录）保证。
    assetsDir: '',
    emptyOutDir: true,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        // 全部平铺到 outDir 根目录，避免出现子目录导致 remoteEntry.js 相对引用失效
        entryFileNames: '[name].js',
        chunkFileNames: '[name]-[hash].js',
        assetFileNames: '[name]-[hash][extname]',
      },
    },
  },
})
