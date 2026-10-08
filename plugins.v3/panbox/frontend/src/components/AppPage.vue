<script setup>
/**
 * PanBox 主界面侧栏整页（Vue 联邦暴露名 `./AppPage`，nav_key = main）。
 *
 * 宿主契约（对照 MoviePilot V3.1.1 前端 `plugin-app` 路由核实）：
 * - 加载顺序为 `AppPage<NavKey>` → `AppPage` → `Page`；nav_key = main 时直接取 `AppPage`；
 * - props：`api`、`navKey`、`pluginId`、`sourcePluginId`、`nativeSubscribe`；
 * - emits：`action`（宿主当前实现为空操作，仅作为扩展点）。
 *
 * 本页只读展示配置状态 + 调用插件 API，**不写配置**（配置由 Config.vue 经宿主保存）。
 */
import { computed, onMounted, ref, watch } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { useNotifier } from '../composables/useNotifier'
import AccountPanel from './panels/AccountPanel.vue'
import FavoritesPanel from './panels/FavoritesPanel.vue'
import HistoryPanel from './panels/HistoryPanel.vue'
import SearchPanel from './panels/SearchPanel.vue'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 侧栏导航键，默认 main */
  navKey: { type: String, default: 'main' },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（本插件未使用，仅保留契约） */
  nativeSubscribe: { type: Object, default: null },
})

const emit = defineEmits(['action'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

/** 页签定义：key 同时用于 navKey 映射 */
const TABS = [
  { key: 'search', title: '搜索', icon: 'mdi-magnify' },
  { key: 'history', title: '历史', icon: 'mdi-history' },
  { key: 'favorites', title: '收藏', icon: 'mdi-star-outline' },
  { key: 'account', title: '账号', icon: 'mdi-account-cog-outline' },
]

/**
 * 把宿主传入的 navKey 映射到页签（如 nav_key = favorites 时直接进入收藏页）。
 *
 * :param navKey: 宿主导航键
 * :return: 页签 key
 */
function tabFromNavKey(navKey) {
  const key = String(navKey || 'main').trim().toLowerCase()
  const matched = TABS.find((tab) => tab.key === key)
  return matched ? matched.key : 'search'
}

const tab = ref(tabFromNavKey(props.navKey))
/** 已访问过的页签（懒加载，避免一次性触发全部请求） */
const visited = ref([tab.value])
const meta = ref(null)
const metaError = ref('')
const loadingMeta = ref(false)

const activeIndex = computed(() => TABS.findIndex((entry) => entry.key === tab.value))
const navKeyLabel = computed(() => props.navKey || 'main')

/**
 * 读取插件状态摘要。
 */
async function loadMeta() {
  loadingMeta.value = true
  metaError.value = ''
  try {
    const response = await client.meta()
    if (response?.success === false) {
      throw new Error(readError(response, '读取插件状态失败'))
    }
    meta.value = response?.data || {}
  } catch (error) {
    metaError.value = readError(error, '读取插件状态失败')
  } finally {
    loadingMeta.value = false
  }
}

watch(tab, (value) => {
  if (!visited.value.includes(value)) visited.value = [...visited.value, value]
})

watch(
  () => props.navKey,
  (value) => {
    const next = tabFromNavKey(value)
    tab.value = next
    if (!visited.value.includes(next)) visited.value = [...visited.value, next]
  },
)

onMounted(() => {
  emit('action', { type: 'app-page-mounted', pluginId: props.pluginId, navKey: props.navKey })
  loadMeta()
})
</script>

<template>
  <div class="panbox-app-page">
    <div class="d-flex flex-wrap align-center ga-2 mb-3">
      <v-icon icon="mdi-cloud-search-outline" color="primary" size="30" />
      <div>
        <div class="text-h6">网盘助手</div>
        <div class="text-caption text-medium-emphasis">
          导航键 {{ navKeyLabel }} · 插件 {{ pluginId || 'PanBox' }}
        </div>
      </div>
      <v-chip v-if="meta" size="small" variant="tonal">v{{ meta.version || '—' }}</v-chip>
      <v-chip v-if="meta" size="small" :color="meta.enabled ? 'success' : 'error'" variant="flat">
        {{ meta.enabled ? '已启用' : '未启用' }}
      </v-chip>
      <v-chip v-if="meta" size="small" :color="meta.p115?.enabled ? 'primary' : 'grey'" variant="tonal">
        115 {{ meta.p115?.enabled ? '已开启' : '未开启' }}
      </v-chip>
      <v-spacer />
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" :loading="loadingMeta" @click="loadMeta">
        刷新状态
      </v-btn>
    </div>

    <v-alert v-if="metaError" type="error" variant="tonal" density="compact" class="mb-3">
      {{ metaError }}
    </v-alert>

    <v-alert v-if="meta && !meta.enabled" type="warning" variant="tonal" density="compact" class="mb-3">
      插件未启用：搜索与转存接口都会返回「插件未启用」。请到插件设置中开启后重试。
    </v-alert>

    <v-tabs v-model="tab" color="primary" density="comfortable" show-arrows>
      <v-tab v-for="entry in TABS" :key="entry.key" :value="entry.key" :prepend-icon="entry.icon">
        {{ entry.title }}
      </v-tab>
    </v-tabs>

    <v-divider class="mb-4" />

    <div v-if="activeIndex < 0" class="text-body-2">未知页签：{{ tab }}</div>

    <SearchPanel
      v-if="tab === 'search'"
      :api="api"
      :channels="meta?.channels || []"
      :default-limit="meta?.search_limit || 30"
      @meta="(value) => (meta = value)"
    />

    <HistoryPanel v-else-if="tab === 'history' && visited.includes('history')" :api="api" @changed="loadMeta" />

    <FavoritesPanel v-else-if="tab === 'favorites' && visited.includes('favorites')" :api="api" @changed="loadMeta" />

    <AccountPanel
      v-else-if="tab === 'account' && visited.includes('account')"
      :api="api"
      @meta="(value) => (meta = value)"
      @action="(payload) => emit('action', payload)"
    />

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">
      {{ text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-app-page {
  padding: 16px;
}
</style>
