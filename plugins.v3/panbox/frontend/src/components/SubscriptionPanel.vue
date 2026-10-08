<script setup>
/**
 * 网盘订阅面板（电影 / 剧集共用）。
 *
 * 由 `AppPageMovie.vue` / `AppPageTv.vue` 分别以 `mediaType` 实例化，对应侧栏
 * 「订阅」分组下的两个入口（仿宿主「订阅 → 电影 / 电视剧」）。
 *
 * 每条订阅展示：海报、标题、年份、启停状态、最近一次搜索结论、已转存数量与记录；
 * 可用操作：立即搜索（执行一次「搜索 + 转存」）、暂停/启用、删除、加入订阅。
 */
import { computed, onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { useNotifier } from '../composables/useNotifier'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 订阅类型：movie / tv */
  mediaType: { type: String, default: 'movie' },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 导航键（movie / tv） */
  navKey: { type: String, default: '' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（保留契约） */
  nativeSubscribe: { type: Object, default: null },
})

const emit = defineEmits(['action'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

const list = ref([])
const loading = ref(false)
const errorText = ref('')
const runningId = ref('')
const runningAll = ref(false)
const expanded = ref('')

const addOpen = ref(false)
const addKeyword = ref('')
const addLoading = ref(false)
const addResults = ref([])
const addError = ref('')

const isTv = computed(() => props.mediaType === 'tv')
const pageTitle = computed(() => (isTv.value ? '网盘剧集订阅' : '网盘电影订阅'))
const enabledCount = computed(() => list.value.filter((item) => item.enabled).length)
const transferredTotal = computed(() => list.value.reduce((sum, item) => sum + (item.transferred_count || 0), 0))

/**
 * 加载订阅列表。
 */
async function load() {
  loading.value = true
  errorText.value = ''
  try {
    const response = await client.subscriptions(props.mediaType)
    if (response?.success === false) throw new Error(readError(response, '订阅加载失败'))
    list.value = response?.data || []
  } catch (err) {
    errorText.value = readError(err, '订阅加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 立即执行单个订阅的同步。
 *
 * :param subscription: 订阅对象
 */
async function runOne(subscription) {
  runningId.value = subscription.id
  try {
    const response = await client.subscriptionRun({ id: subscription.id })
    if (response?.success === false) throw new Error(readError(response, '执行失败'))
    const report = (response?.reports || [])[0] || {}
    toast(report.message || response?.message || '已执行', report.transferred ? 'success' : 'info')
    await load()
  } catch (err) {
    toast(readError(err, '执行失败'), 'error')
  } finally {
    runningId.value = ''
  }
}

/**
 * 立即执行该类型下全部订阅。
 */
async function runAll() {
  runningAll.value = true
  try {
    const response = await client.subscriptionRun({ media_type: props.mediaType })
    if (response?.success === false) throw new Error(readError(response, '执行失败'))
    toast(response?.message || '已执行', 'success')
    await load()
  } catch (err) {
    toast(readError(err, '执行失败'), 'error')
  } finally {
    runningAll.value = false
  }
}

/**
 * 切换订阅启用状态。
 *
 * :param subscription: 订阅对象
 */
async function toggle(subscription) {
  try {
    const response = await client.subscriptionUpdate({ id: subscription.id, enabled: !subscription.enabled })
    if (response?.success === false) throw new Error(readError(response, '更新失败'))
    await load()
  } catch (err) {
    toast(readError(err, '更新失败'), 'error')
  }
}

/**
 * 删除订阅。
 *
 * :param subscription: 订阅对象
 */
async function remove(subscription) {
  if (!window.confirm(`确定删除订阅「${subscription.title}」？其转存记录也会一并移除。`)) return
  try {
    const response = await client.subscriptionDelete(subscription.id)
    if (response?.success === false) throw new Error(readError(response, '删除失败'))
    toast('已删除订阅', 'success')
    await load()
  } catch (err) {
    toast(readError(err, '删除失败'), 'error')
  }
}

/**
 * 在新增对话框里搜索媒体条目。
 */
async function searchMedia() {
  const keyword = addKeyword.value.trim()
  if (!keyword) return
  addLoading.value = true
  addError.value = ''
  try {
    const response = await client.mediaSearch({ keyword, media_type: props.mediaType })
    addResults.value = response?.data || []
    if (!addResults.value.length) addError.value = '没有匹配的条目'
  } catch (err) {
    addError.value = readError(err, '搜索失败')
  } finally {
    addLoading.value = false
  }
}

/**
 * 把选中的媒体条目加入订阅。
 *
 * :param media: 媒体条目
 */
async function addSubscription(media) {
  try {
    const response = await client.subscriptionAdd({
      title: media.title,
      media_type: props.mediaType,
      year: media.year,
      poster: media.poster,
      media_source: media.media_source,
      media_id: media.media_id,
      tmdb_id: media.tmdb_id,
      douban_id: media.douban_id,
    })
    if (response?.success === false) throw new Error(readError(response, '订阅失败'))
    toast(`已订阅：${media.title}`, 'success')
    addOpen.value = false
    addKeyword.value = ''
    addResults.value = []
    await load()
    emit('action')
  } catch (err) {
    toast(readError(err, '订阅失败'), 'error')
  }
}

/**
 * 把时间戳格式化为可读文本。
 *
 * :param value: Unix 秒
 * :return: 展示文本
 */
function formatTime(value) {
  if (!value) return '尚未执行'
  const date = new Date(value * 1000)
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<template>
  <div class="pbx-subs">
    <div class="pbx-subs__bar">
      <span class="pbx-subs__title">{{ pageTitle }}</span>
      <span class="pbx-subs__stat">共 {{ list.length }} 个 · 启用 {{ enabledCount }} 个 · 已转存 {{ transferredTotal }} 个资源</span>
      <v-spacer />
      <v-btn
        size="small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-sync"
        :loading="runningAll"
        @click="runAll"
      >
        立即同步全部
      </v-btn>
      <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-plus" @click="addOpen = true">
        新增订阅
      </v-btn>
    </div>

    <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mb-2">{{ errorText }}</v-alert>

    <div v-if="loading" class="pbx-subs__empty">正在加载…</div>
    <v-alert v-else-if="!list.length" type="info" variant="tonal" density="compact">
      还没有{{ isTv ? '剧集' : '电影' }}订阅。点「新增订阅」搜索影视条目，或到「网盘资源」页里点条目上的「订阅」。
    </v-alert>

    <div v-else class="pbx-subs__list">
      <v-card v-for="subscription in list" :key="subscription.id" class="pbx-sub" flat>
        <img v-if="subscription.poster_url" :src="subscription.poster_url" class="pbx-sub__poster" :alt="subscription.title" />
        <div v-else class="pbx-sub__poster pbx-sub__poster--empty">
          <v-icon icon="mdi-movie-outline" size="22" />
        </div>

        <div class="pbx-sub__main">
          <div class="pbx-sub__title">
            {{ subscription.title }}
            <span v-if="subscription.year" class="pbx-sub__year">{{ subscription.year }}</span>
          </div>
          <div class="pbx-sub__chips">
            <span class="pbx-chip" :class="subscription.enabled ? 'pbx-chip--on' : 'pbx-chip--off'">
              {{ subscription.enabled ? '订阅中' : '已暂停' }}
            </span>
            <span v-if="subscription.season" class="pbx-chip pbx-chip--muted">第 {{ subscription.season }} 季</span>
            <span class="pbx-chip pbx-chip--muted">已转存 {{ subscription.transferred_count || 0 }}</span>
            <span v-if="subscription.prefer_keywords" class="pbx-chip pbx-chip--muted">偏好：{{ subscription.prefer_keywords }}</span>
          </div>
          <div class="pbx-sub__status">
            <v-icon icon="mdi-history" size="13" />
            <span>{{ formatTime(subscription.last_run_at) }} · {{ subscription.last_message || '尚未执行' }}</span>
          </div>

          <div v-if="expanded === subscription.id && (subscription.transferred || []).length" class="pbx-sub__records">
            <div v-for="(record, index) in subscription.transferred.slice(-10).reverse()" :key="index" class="pbx-sub__record">
              <span class="pbx-sub__record-title">{{ record.title || record.file_name || record.url }}</span>
              <span class="pbx-sub__record-meta">
                <template v-if="record.size_gb"> {{ record.size_gb }} GB ·</template>
                {{ formatTime(record.at) }}
              </span>
            </div>
          </div>
        </div>

        <div class="pbx-sub__actions">
          <v-btn
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-magnify"
            :loading="runningId === subscription.id"
            @click="runOne(subscription)"
          >
            立即搜索
          </v-btn>
          <v-btn size="small" variant="text" :prepend-icon="subscription.enabled ? 'mdi-pause' : 'mdi-play'" @click="toggle(subscription)">
            {{ subscription.enabled ? '暂停' : '启用' }}
          </v-btn>
          <v-btn
            v-if="(subscription.transferred || []).length"
            size="small"
            variant="text"
            :prepend-icon="expanded === subscription.id ? 'mdi-chevron-up' : 'mdi-chevron-down'"
            @click="expanded = expanded === subscription.id ? '' : subscription.id"
          >
            记录
          </v-btn>
          <v-btn size="small" variant="text" color="error" prepend-icon="mdi-delete-outline" @click="remove(subscription)">
            删除
          </v-btn>
        </div>
      </v-card>
    </div>

    <!-- 新增订阅：搜索影视条目 -->
    <v-dialog v-model="addOpen" max-width="44rem" scrollable>
      <v-card class="pbx-add">
        <v-card-title class="pbx-add__title">新增{{ isTv ? '剧集' : '电影' }}订阅</v-card-title>
        <v-card-text>
          <div class="pbx-add__search">
            <v-text-field
              v-model="addKeyword"
              :placeholder="isTv ? '搜索剧集名称，如：末日地堡' : '搜索电影名称，如：沙丘 2'"
              density="compact"
              variant="outlined"
              hide-details
              prepend-inner-icon="mdi-magnify"
              @keyup.enter="searchMedia"
            />
            <v-btn size="small" color="primary" variant="flat" :loading="addLoading" @click="searchMedia">搜索</v-btn>
          </div>
          <v-alert v-if="addError" type="info" variant="tonal" density="compact" class="mt-2">{{ addError }}</v-alert>

          <div class="pbx-add__results">
            <div v-for="(media, index) in addResults" :key="`${media.media_id}-${index}`" class="pbx-add__item">
              <img v-if="media.poster" :src="media.poster" class="pbx-add__poster" :alt="media.title" />
              <div v-else class="pbx-add__poster pbx-add__poster--empty"><v-icon icon="mdi-movie-outline" size="18" /></div>
              <div class="pbx-add__info">
                <div class="pbx-add__name">{{ media.title }}</div>
                <div class="pbx-add__meta">
                  {{ media.year || '—' }}
                  <template v-if="media.vote_average"> · 评分 {{ media.vote_average.toFixed(1) }}</template>
                  <template v-if="media.media_source"> · {{ media.media_source }}</template>
                </div>
              </div>
              <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-bell-plus-outline" @click="addSubscription(media)">
                订阅
              </v-btn>
            </div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addOpen = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">{{ text }}</v-snackbar>
  </div>
</template>

<style scoped>
.pbx-subs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 16px;
  min-height: 0;
}

.pbx-subs__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pbx-subs__title {
  font-size: 0.9375rem;
  font-weight: 600;
}

.pbx-subs__stat {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.pbx-subs__empty {
  font-size: 0.8125rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
  padding: 8px 0;
}

.pbx-subs__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.pbx-sub {
  display: flex;
  gap: 10px;
  padding: 8px;
  align-items: flex-start;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.pbx-sub__poster {
  width: 4rem;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: 6px;
  flex: 0 0 auto;
}

.pbx-sub__poster--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.08);
  opacity: 0.6;
}

.pbx-sub__main {
  flex: 1 1 auto;
  min-width: 0;
}

.pbx-sub__title {
  font-size: 0.875rem;
  font-weight: 600;
}

.pbx-sub__year {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-left: 4px;
  font-weight: 400;
}

.pbx-sub__chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin: 3px 0 4px;
}

.pbx-chip {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 0.6875rem;
  border: 1px solid transparent;
}

.pbx-chip--on {
  color: rgb(var(--v-theme-success));
  background: rgba(var(--v-theme-success), 0.12);
  border-color: rgba(var(--v-theme-success), 0.3);
}

.pbx-chip--off {
  color: rgba(var(--v-theme-on-surface), 0.6);
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.pbx-chip--muted {
  color: rgba(var(--v-theme-on-surface), 0.65);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-color: rgba(var(--v-border-color), 0.5);
}

.pbx-sub__status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.pbx-sub__records {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pbx-sub__record {
  display: flex;
  gap: 6px;
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.pbx-sub__record-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pbx-sub__record-meta {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
}

.pbx-sub__actions {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 0 0 auto;
}

.pbx-add__title {
  font-size: 0.9375rem;
  font-weight: 600;
  padding-bottom: 4px;
}

.pbx-add__search {
  display: flex;
  gap: 6px;
  align-items: center;
}

.pbx-add__results {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 60vh;
  overflow-y: auto;
}

.pbx-add__item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 5px;
  border-radius: 7px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.pbx-add__poster {
  width: 2.5rem;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: 4px;
}

.pbx-add__poster--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.pbx-add__info {
  flex: 1 1 auto;
  min-width: 0;
}

.pbx-add__name {
  font-size: 0.8125rem;
  font-weight: 600;
}

.pbx-add__meta {
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

@media (max-width: 720px) {
  .pbx-sub {
    flex-wrap: wrap;
  }

  .pbx-sub__actions {
    flex-direction: row;
    flex-wrap: wrap;
    width: 100%;
  }
}
</style>
