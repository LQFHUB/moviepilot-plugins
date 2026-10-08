<script setup>
/**
 * PanBox 插件详情页组件（Vue 联邦暴露名 `./Page`）。
 *
 * 宿主契约（对照 MoviePilot V3.1.1 前端 `PluginDataDialog` 核实）：
 * - props：`api`、`pluginId`、`sourcePluginId`、`nativeSubscribe`、`showSwitch`；
 * - emits：`action`、`layout`（`{ maxWidth }`）、`switch`（切到插件配置）、`close`。
 *
 * 这里是精简版：搜索 + 结果列表（转存 / 收藏），完整的历史、收藏与账号管理在侧栏整页（AppPage）。
 */
import { onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { useNotifier } from '../composables/useNotifier'
import SearchPanel from './panels/SearchPanel.vue'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（本插件未使用，仅保留契约） */
  nativeSubscribe: { type: Object, default: null },
  /** 宿主是否允许切换到配置页 */
  showSwitch: { type: Boolean, default: false },
})

const emit = defineEmits(['action', 'layout', 'switch', 'close'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

const meta = ref(null)
const metaError = ref('')

/**
 * 读取插件状态摘要。
 */
async function loadMeta() {
  metaError.value = ''
  try {
    const response = await client.meta()
    if (response?.success === false) {
      throw new Error(readError(response, '读取插件状态失败'))
    }
    meta.value = response?.data || {}
  } catch (error) {
    metaError.value = readError(error, '读取插件状态失败')
  }
}

onMounted(() => {
  emit('layout', { maxWidth: '80rem' })
  emit('action', { type: 'page-mounted', pluginId: props.pluginId })
  loadMeta()
})
</script>

<template>
  <div class="panbox-page">
    <div class="d-flex flex-wrap align-center ga-2 mb-3">
      <v-icon icon="mdi-cloud-search-outline" color="primary" size="28" />
      <span class="text-h6">网盘助手</span>
      <v-chip v-if="meta" size="small" variant="tonal">v{{ meta.version || '—' }}</v-chip>
      <v-chip v-if="meta" size="small" :color="meta.enabled ? 'success' : 'error'" variant="flat">
        {{ meta.enabled ? '已启用' : '未启用' }}
      </v-chip>
      <v-chip v-if="meta" size="small" :color="meta.p115?.enabled ? 'primary' : 'grey'" variant="tonal">
        115 {{ meta.p115?.enabled ? '已开启' : '未开启' }}
      </v-chip>
      <v-chip v-if="meta" size="small" :color="meta.p115?.configured ? 'primary' : 'warning'" variant="tonal">
        Cookie {{ meta.p115?.configured ? '已配置' : '未配置' }}
      </v-chip>
      <v-spacer />
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="loadMeta">刷新状态</v-btn>
    </div>

    <v-alert v-if="metaError" type="error" variant="tonal" density="compact" class="mb-3">
      {{ metaError }}
    </v-alert>

    <v-alert v-if="meta && !meta.enabled" type="warning" variant="tonal" density="compact" class="mb-3">
      插件当前未启用，搜索与转存接口都会返回「插件未启用」。请在插件设置中开启。
    </v-alert>

    <v-alert v-else-if="meta && !meta.p115?.enabled" type="info" variant="tonal" density="compact" class="mb-3">
      115 转存未开启，仍可搜索与复制链接；如需一键转存，请在插件设置中开启并配置 Cookie。
    </v-alert>

    <SearchPanel :api="api" :channels="meta?.channels || []" :default-limit="meta?.search_limit || 30" compact @meta="(value) => (meta = value)" />

    <div class="text-caption text-medium-emphasis mt-4">
      提示：历史记录、收藏列表与 115 账号管理请从主界面侧栏「网盘助手」进入完整页面。
    </div>

    <v-card-actions class="px-0 mt-2">
      <v-btn v-if="showSwitch" variant="text" prepend-icon="mdi-cog-outline" @click="emit('switch')">插件设置</v-btn>
      <v-spacer />
      <v-btn variant="text" prepend-icon="mdi-close" @click="emit('close')">关闭</v-btn>
    </v-card-actions>

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">
      {{ text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-page {
  padding: 8px 16px 16px;
}
</style>
