/**
 * 本地开发引导（仅 `npm run dev` 使用）。
 *
 * 生产构建时 `import.meta.env.DEV` 为 false，该动态导入会被整体摇树移除，
 * 因此 `index.html` / `src/main.js` 不会把 Vuetify、调试台等代码带进联邦产物。
 */
if (import.meta.env.DEV) {
  import('./dev/dev-boot.js')
}
