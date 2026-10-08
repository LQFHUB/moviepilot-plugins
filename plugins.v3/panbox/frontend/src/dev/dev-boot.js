/**
 * 调试台启动脚本（仅开发环境执行）。
 *
 * 这里才引入 Vuetify 与调试台组件；生产构建不会包含该模块。
 *
 * 注意：必须**显式**把 `vuetify/components` 与 `vuetify/directives` 传给
 * `createVuetify({ components, directives })`。只写 `createVuetify()` 时，
 * 联邦插件的 dev 共享别名会导致组件未注册（控制台刷
 * 「Failed to resolve component: v-btn」之类告警，页面渲染成未解析的自定义标签）。
 * 实测于 @originjs/vite-plugin-federation 1.4.1 + vuetify 3.7.3。
 */
import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'

import DevApp from './DevApp.vue'

const app = createApp(DevApp)
app.use(createVuetify({ components, directives }))
app.mount('#app')
