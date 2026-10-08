<script setup>
/**
 * 「网盘剧集订阅」页（联邦暴露名 `./AppPageTv`，侧栏 section=subscribe，nav_key=tv）。
 *
 * 复用 `SubscriptionPanel`，与「网盘电影订阅」仅 `mediaType` 不同。
 */
import SubscriptionPanel from './SubscriptionPanel.vue'

defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 导航键 */
  navKey: { type: String, default: 'tv' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（保留契约） */
  nativeSubscribe: { type: Object, default: null },
})

const emit = defineEmits(['action'])
</script>

<template>
  <SubscriptionPanel
    :api="api"
    media-type="tv"
    :plugin-id="pluginId"
    :nav-key="navKey || 'tv'"
    :source-plugin-id="sourcePluginId"
    @action="emit('action')"
  />
</template>
