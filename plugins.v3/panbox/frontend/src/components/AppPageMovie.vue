<script setup>
/**
 * 「网盘电影订阅」页（联邦暴露名 `./AppPageMovie`，侧栏 section=subscribe，nav_key=movie）。
 *
 * 复用 `SubscriptionPanel`，与「网盘剧集订阅」仅 `mediaType` 不同——对齐宿主
 * 「订阅 → 电影 / 电视剧」的分栏习惯。
 */
import SubscriptionPanel from './SubscriptionPanel.vue'

defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 导航键 */
  navKey: { type: String, default: 'movie' },
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
    media-type="movie"
    :plugin-id="pluginId"
    :nav-key="navKey || 'movie'"
    :source-plugin-id="sourcePluginId"
    @action="emit('action')"
  />
</template>
