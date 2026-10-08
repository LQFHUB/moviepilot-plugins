<script setup>
/**
 * PanBox「网盘资源」页（联邦暴露名 `./AppPageResource`，侧栏 section=discovery）。
 *
 * 交互与视觉对齐宿主「探索」菜单：豆瓣 / TMDB 两个数据源的榜单页签 + 榜单排序，
 * 点开某个影视条目后进入详情对话框——按**频道页签**列出该条目在各 Telegram 频道中的
 * 网盘资源（复用 `ResourceCard` 的复制/收藏/转存交互）。
 *
 * 说明：海报与元数据全部来自宿主链（豆瓣 / TMDB），本组件不直接访问第三方站点。
 */
import { computed, onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { useResourceActions } from '../composables/useResourceActions'
import ResourceCard from './common/ResourceCard.vue'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 导航键（本页为 resource） */
  navKey: { type: String, default: 'resource' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（保留契约） */
  nativeSubscribe: { type: Object, default: null },
})

const emit = defineEmits(['action'])

const client = createPanBoxApi(props.api)
// 复用统一的资源动作与提示条（内部已带 notifier，故本组件不再另建 snackbar）
const { isBusy, transfer, favorite, toast, visible, text, color } = useResourceActions(props.api)

const tabs = ref([])
const activeTab = ref('')
const activeSort = ref('')
const items = ref([])
const loading = ref(false)
const errorText = ref('')
const meta = ref({})

/** 搜索态：非空表示正在展示搜索结果 */
const keyword = ref('')
const searchMode = ref(false)

/** 详情对话框状态 */
const detailOpen = ref(false)
const detailMedia = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const channelBuckets = ref([])
const activeChannel = ref('')

const currentTab = computed(() => tabs.value.find((item) => item.key === activeTab.value) || null)
const currentSorts = computed(() => currentTab.value?.sorts || [])
const activeBucket = computed(
  () => channelBuckets.value.find((entry) => entry.channel_id === activeChannel.value) || null,
)
/** 115 是否已就绪（顶部状态提示） */
const p115Ready = computed(() => Boolean(meta.value?.p115?.enabled) && Boolean(meta.value?.p115?.configured))

/**
 * 加载榜单页签并渲染首个页签。
 */
async function bootstrap() {
  try {
    const tabsResponse = await client.discoverTabs()
    tabs.value = tabsResponse?.data || []
    const info = await client.meta()
    meta.value = info?.data || {}
    if (tabs.value.length) {
      activeTab.value = tabs.value[0].key
      activeSort.value = tabs.value[0].sorts?.[0]?.value || ''
      await loadRank()
    }
  } catch (err) {
    errorText.value = readError(err, '初始化失败')
  }
}

/**
 * 按当前页签与排序加载榜单。
 */
async function loadRank() {
  if (!activeTab.value) return
  loading.value = true
  errorText.value = ''
  searchMode.value = false
  try {
    const response = await client.discoverRank({ key: activeTab.value, sort: activeSort.value, count: 30 })
    items.value = response?.data || []
    if (!items.value.length) errorText.value = '该榜单暂无数据（可在插件设置里检查豆瓣/TMDB 账号或代理）'
  } catch (err) {
    errorText.value = readError(err, '榜单加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 切换榜单页签。
 *
 * :param key: 页签 key
 */
async function onTabChange(key) {
  activeTab.value = key
  const tab = tabs.value.find((item) => item.key === key)
  activeSort.value = tab?.sorts?.[0]?.value || ''
  await loadRank()
}

/**
 * 切换榜单排序。
 *
 * :param value: 排序取值
 */
async function onSortChange(value) {
  activeSort.value = value
  await loadRank()
}

/**
 * 按标题搜索影视条目。
 */
async function doSearch() {
  const text0 = keyword.value.trim()
  if (!text0) return
  loading.value = true
  errorText.value = ''
  try {
    const response = await client.mediaSearch({ keyword: text0 })
    items.value = response?.data || []
    searchMode.value = true
    if (!items.value.length) errorText.value = `未找到与「${text0}」匹配的影视条目`
  } catch (err) {
    errorText.value = readError(err, '搜索失败')
  } finally {
    loading.value = false
  }
}

/**
 * 退出搜索态，回到榜单。
 */
async function exitSearch() {
  keyword.value = ''
  searchMode.value = false
  await loadRank()
}

/**
 * 打开某条目的资源详情（按频道分组）。
 *
 * :param media: 媒体条目
 */
async function openDetail(media) {
  detailMedia.value = media
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = ''
  channelBuckets.value = []
  activeChannel.value = ''
  try {
    const response = await client.mediaResources({
      title: media.title,
      media_type: media.media_type,
      season: media.season || 0,
    })
    channelBuckets.value = response?.channels || []
    activeChannel.value = channelBuckets.value[0]?.channel_id || ''
    if (!channelBuckets.value.length) detailError.value = '配置的频道里暂未找到该条目的网盘资源'
  } catch (err) {
    detailError.value = readError(err, '搜索频道资源失败')
  } finally {
    detailLoading.value = false
  }
}

/**
 * 把条目加入网盘订阅（电影 / 剧集分别落到对应侧栏页）。
 *
 * :param media: 媒体条目
 */
async function subscribe(media) {
  try {
    const response = await client.subscriptionAdd({
      title: media.title,
      media_type: media.media_type,
      year: media.year,
      poster: media.poster,
      media_source: media.media_source,
      media_id: media.media_id,
      tmdb_id: media.tmdb_id,
      douban_id: media.douban_id,
    })
    if (response?.success === false) throw new Error(readError(response, '订阅失败'))
    toast(`已加入「网盘${media.media_type === 'tv' ? '剧集' : '电影'}订阅」：${media.title}`, 'success')
    emit('action')
  } catch (err) {
    toast(readError(err, '订阅失败'), 'error')
  }
}

/**
 * 转存单条资源（busy 状态与提示条由 composable 统一管理）。
 *
 * :param item: 资源条目
 * :param link: 被点击的网盘链接对象
 */
async function onTransfer(item, link) {
  await transfer(item, link)
}

/**
 * 收藏单条资源。
 *
 * :param item: 资源条目
 */
async function onFavorite(item) {
  await favorite(item)
}

onMounted(bootstrap)
</script>

<template>
  <div class="pbx-resource">
    <!-- 顶栏：榜单页签 + 搜索 -->
    <div class="pbx-resource__bar">
      <div class="pbx-resource__tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="pbx-tab"
          :class="{ 'pbx-tab--active': !searchMode && activeTab === tab.key }"
          @click="onTabChange(tab.key)"
        >
          <v-icon :icon="tab.icon" size="14" />
          <span>{{ tab.title }}</span>
        </button>
      </div>
      <v-spacer />
      <div class="pbx-resource__search">
        <v-text-field
          v-model="keyword"
          placeholder="搜索影视条目，如：沙丘 2"
          density="compact"
          variant="outlined"
          hide-details
          prepend-inner-icon="mdi-magnify"
          @keyup.enter="doSearch"
        />
        <v-btn size="small" color="primary" variant="flat" @click="doSearch">搜索</v-btn>
      </div>
    </div>

    <!-- 榜单排序（搜索态隐藏） -->
    <div v-if="!searchMode && currentSorts.length" class="pbx-resource__sorts">
      <v-chip
        v-for="option in currentSorts"
        :key="option.value"
        size="x-small"
        :variant="activeSort === option.value ? 'flat' : 'tonal'"
        :color="activeSort === option.value ? 'primary' : undefined"
        @click="onSortChange(option.value)"
      >
        {{ option.label }}
      </v-chip>
      <span class="pbx-resource__hint">
        数据源：{{ currentTab?.source === 'tmdb' ? 'TMDB' : '豆瓣' }} · 共 {{ items.length }} 条
      </span>
    </div>

    <div v-if="searchMode" class="pbx-resource__sorts">
      <v-icon icon="mdi-magnify" size="14" />
      <span class="pbx-resource__hint">「{{ keyword }}」的搜索结果，共 {{ items.length }} 条</span>
      <v-btn size="x-small" variant="text" prepend-icon="mdi-arrow-left" @click="exitSearch">返回榜单</v-btn>
    </div>

    <div v-if="!p115Ready" class="pbx-resource__sorts">
      <v-icon icon="mdi-alert-circle-outline" size="14" />
      <span class="pbx-resource__hint">115 未就绪：可在「网盘助手 → 设置」中开启并配置 Cookie，否则只能复制链接</span>
    </div>

    <v-alert v-if="errorText" type="info" variant="tonal" density="compact" class="mb-2">{{ errorText }}</v-alert>

    <!-- 海报网格 -->
    <div v-if="loading" class="pbx-grid">
      <div v-for="index in 12" :key="index" class="pbx-card pbx-card--skeleton">
        <div class="pbx-card__poster" />
      </div>
    </div>
    <div v-else class="pbx-grid">
      <button
        v-for="(media, index) in items"
        :key="`${media.media_id}-${index}`"
        type="button"
        class="pbx-card"
        :title="media.title"
        @click="openDetail(media)"
      >
        <span class="pbx-card__poster">
          <img v-if="media.poster" :src="media.poster" :alt="media.title" loading="lazy" />
          <span v-else class="pbx-card__placeholder"><v-icon icon="mdi-movie-outline" size="26" /></span>
          <span v-if="media.vote_average" class="pbx-card__rate">{{ media.vote_average.toFixed(1) }}</span>
          <span class="pbx-card__type">{{ media.media_type === 'tv' ? '剧集' : '电影' }}</span>
        </span>
        <span class="pbx-card__title">{{ media.title }}</span>
        <span class="pbx-card__meta">{{ media.year || '—' }}</span>
      </button>
    </div>

    <!-- 资源详情：频道页签 + 资源卡片 -->
    <v-dialog v-model="detailOpen" max-width="62rem" scrollable>
      <v-card class="pbx-detail">
        <div class="pbx-detail__head">
          <img v-if="detailMedia?.poster" :src="detailMedia.poster" class="pbx-detail__poster" :alt="detailMedia?.title" />
          <div class="pbx-detail__info">
            <div class="pbx-detail__title">
              {{ detailMedia?.title }}
              <span class="pbx-detail__year">{{ detailMedia?.year }}</span>
            </div>
            <div class="pbx-detail__sub">
              {{ detailMedia?.media_type === 'tv' ? '剧集' : '电影' }}
              <template v-if="detailMedia?.vote_average"> · 评分 {{ detailMedia.vote_average.toFixed(1) }}</template>
              <template v-if="detailMedia?.media_source"> · {{ detailMedia.media_source }}</template>
            </div>
            <p v-if="detailMedia?.overview" class="pbx-detail__overview">{{ detailMedia.overview }}</p>
          </div>
          <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-bell-plus-outline" @click="subscribe(detailMedia)">
            订阅
          </v-btn>
          <v-btn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="detailOpen = false" />
        </div>

        <v-divider />

        <div v-if="detailLoading" class="pbx-detail__loading">
          <v-progress-circular indeterminate size="22" /> 正在检索频道资源…
        </div>
        <v-alert v-else-if="detailError" type="info" variant="tonal" density="compact" class="ma-3">{{ detailError }}</v-alert>

        <div v-else class="pbx-detail__body">
          <nav class="pbx-detail__channels" aria-label="频道">
            <button
              v-for="bucket in channelBuckets"
              :key="bucket.channel_id"
              type="button"
              class="pbx-channel-tab"
              :class="{ 'pbx-channel-tab--active': activeChannel === bucket.channel_id }"
              @click="activeChannel = bucket.channel_id"
            >
              <span class="pbx-channel-tab__name">{{ bucket.channel_name }}</span>
              <span class="pbx-channel-tab__count">{{ bucket.items.length }}</span>
            </button>
          </nav>
          <div class="pbx-detail__list">
            <ResourceCard
              v-for="item in (activeBucket?.items || [])"
              :key="`${item.channel_id}-${item.message_id}`"
              :item="item"
              :busy="isBusy(item)"
              @transfer="(link) => onTransfer(item, link)"
              @favorite="onFavorite(item)"
              @copied="toast('链接已复制', 'success')"
              @failed="(message) => toast(message, 'error')"
            />
          </div>
        </div>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">{{ text }}</v-snackbar>
  </div>
</template>

<style scoped>
.pbx-resource {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 16px;
  min-height: 0;
}

.pbx-resource__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pbx-resource__tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.pbx-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 14px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.8);
  font-size: 0.8125rem;
  cursor: pointer;
}

.pbx-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.pbx-tab--active {
  background: rgba(var(--v-theme-primary), 0.14);
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

.pbx-resource__search {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 18rem;
}

.pbx-resource__sorts {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.pbx-resource__hint {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

/* 海报网格 */
.pbx-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr));
  gap: 10px;
  overflow-y: auto;
  padding-bottom: 8px;
}

.pbx-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.pbx-card__poster {
  position: relative;
  display: block;
  aspect-ratio: 2 / 3;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.pbx-card__poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 180ms ease-out;
}

.pbx-card:hover .pbx-card__poster img {
  transform: scale(1.04);
}

.pbx-card__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  opacity: 0.5;
}

.pbx-card__rate,
.pbx-card__type {
  position: absolute;
  bottom: 4px;
  font-size: 0.6875rem;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.62);
  color: #fff;
}

.pbx-card__rate {
  left: 4px;
}

.pbx-card__type {
  right: 4px;
}

.pbx-card__title {
  font-size: 0.75rem;
  line-height: 1.25;
  color: rgba(var(--v-theme-on-surface), 0.9);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pbx-card__meta {
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.pbx-card--skeleton .pbx-card__poster {
  animation: pbx-pulse 1.4s ease-in-out infinite;
}

@keyframes pbx-pulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 0.85; }
}

/* 详情对话框 */
.pbx-detail {
  display: flex;
  flex-direction: column;
  max-height: min(44rem, calc(100dvh - 80px));
}

.pbx-detail__head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
}

.pbx-detail__poster {
  width: 4.5rem;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: 6px;
}

.pbx-detail__info {
  flex: 1 1 auto;
  min-width: 0;
}

.pbx-detail__title {
  font-size: 0.9375rem;
  font-weight: 600;
}

.pbx-detail__year {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-left: 4px;
}

.pbx-detail__sub {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin-top: 1px;
}

.pbx-detail__overview {
  margin: 4px 0 0;
  font-size: 0.75rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.6);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.pbx-detail__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 14px;
  font-size: 0.8125rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.pbx-detail__body {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
}

.pbx-detail__channels {
  display: flex;
  flex-direction: column;
  flex: 0 0 11rem;
  gap: 2px;
  padding: 8px;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow-y: auto;
}

.pbx-channel-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.8);
  font-size: 0.75rem;
  text-align: left;
  cursor: pointer;
}

.pbx-channel-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.pbx-channel-tab--active {
  background: rgba(var(--v-theme-primary), 0.13);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

.pbx-channel-tab__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pbx-channel-tab__count {
  font-size: 0.6875rem;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

.pbx-detail__list {
  flex: 1 1 auto;
  min-width: 0;
  padding: 8px 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (max-width: 720px) {
  .pbx-detail__body {
    flex-direction: column;
  }

  .pbx-detail__channels {
    flex: 0 0 auto;
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    overflow-x: auto;
  }

  .pbx-resource__search {
    min-width: 0;
    width: 100%;
  }
}
</style>
