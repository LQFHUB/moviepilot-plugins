/**
 * 调试台启动脚本（仅开发环境执行）。
 *
 * 这里才引入 Vuetify 与调试台组件；生产构建不会包含该模块。
 */
import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import 'vuetify/styles'

import DevApp from './DevApp.vue'

createApp(DevApp).use(createVuetify()).mount('#app')
