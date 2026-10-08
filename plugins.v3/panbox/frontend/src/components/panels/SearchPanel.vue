<script setup>
/**
 * 搜索面板：关键词 + 频道多选 → 调用 `plugin/PanBox/search` → 结果列表。
 *
 * 后端 `/search` 只接受单个 `channel_id`，因此：
 * - 未选择或全选频道时，不传 `channel_id`（后端一次性搜索全部配置频道）；
 * - 选择 2 个及以上频道时，按频道逐个请求后合并结果（顺序执行，避免给 Telegram 造成并发热点）。
 */
import { computed, onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../../utils/api'
import { itemKey } from '../../utils/cloud'
import { useResourceActions } from '../../composables/useResourceActions'
import ResourceCard from '../common/ResourceCard.vue'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 频道列表（缺省时组件自行读取 meta） */
  channels: { type: Array, default: () => [] },
  /** 每频道结果上限默认值 */
  defaultLimit: { type: Number, default: 30 },
  /** 精简模式（详情对话框内使用） */
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['meta', 'stats'])

const client = createPanBoxApi(props.api)
const { busyCount, isBusy, transfer, favorite, snackbar, toast } = useResourceActions(props.api)

const keyword = ref('')
const selectedChannels = ref([])
const limit = ref(props.defaultLimit)
const loading = ref(false)
const progressText = ref('')
const items = ref([])
const errors = ref([])
const elapsed = ref(0)
const searched = ref(false)
const metaChannels = ref(Array.isArray(props.channels) ? props.channels : [])

const channelItems = computed(() =>
  (metaChannels.value.length ? metaChannels.value : props.channels).map((channel) => ({
    title: channel.name ? `${channel.name}（${channel.id}）` : channel.id,
    value: channel.id,
  })),
)

/** 结果条数统计（去重后） */
const resultCount = computed(() => items.value.length)

onMounted(async () => {
  if (metaChannels.value.length) return
  try {
    const response = await client.meta()
    if (response?.success === false) return
    const data = response?.data || {}
    metaChannels.value = Array.isArray(data.channels) ? data.channels : []
    if (data.search_limit) limit.value = Number(data.search_limit)
    emit('meta', data)
  } catch (error) {
    toast(readError(error, '读取插件状态失败'), 'error')
  }
})

/**
 * 执行搜索。
 */
async function runSearch() {
  if (loading.value) return
  const channels = metaChannels.value.length ? metaChannels.value : props.channels
  const allIds = channels.map((channel) => channel.id)
  const picked = selectedChannels.value.filter((id) => allIds.includes(id))
  // 未选择或全选 → 交给后端一次搜索全部配置频道
  const targets = !picked.length || picked.length === allIds.length ? [''] : picked

  loading.value = true
  searched.value = true
  progressText.value = ''
  const localErrors = []
  const bucket = new Map()
  const started = Date.now()
  try {
    for (let index = 0; index < targets.length; index += 1) {
      const channelId = targets[index]
      const label = channelId ? channels.find((entry) => entry.id === channelId)?.name || channelId : '全部频道'
      progressText.value = `正在搜索：${label}（${index + 1}/${targets.length}）`
      try {
        const response = await client.search({
          keyword: keyword.value.trim(),
          channel_id: channelId,
          limit: Number(limit.value) || 0,
          record: true,
        })
        if (response?.success === false) {
          localErrors.push({ channel_id: channelId || '-', message: readError(response, '搜索失败') })
          continue
        }
        for (const item of response?.items || []) {
          bucket.set(itemKey(item), item)
        }
        for (const entry of response?.errors || []) {
          localErrors.push(entry)
        }
      } catch (error) {
        localErrors.push({ channel_id: channelId || '-', message: readError(error, '搜索请求失败') })
      }
    }
    items.value = [...bucket.values()]
    errors.value = localErrors
    elapsed.value = Date.now() - started
    emit('stats', { count: items.value.length, elapsed: elapsed.value })
    if (!items.value.length && localErrors.length) {
      toast('所有频道均搜索失败，请查看下方失败原因', 'error')
    } else if (!items.value.length) {
      toast('没有匹配到资源，换个关键词试试', 'info')
    }
  } finally {
    loading.value = false
    progressText.value = ''
  }
}

/**
 * 处理转存。
 *
 * :param item: ResourceItem
 * :param link: 115 链接
 */
function onTransfer(item, link) {
  transfer(item, link)
}

/**
 * 处理收藏。
 *
 * :param item: ResourceItem
 */
function onFavorite(item) {
  favorite(item)
}
</script>

<template>
  <div class="panbox-search">
    <v-row dense>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="keyword"
          label="关键词"
          placeholder="例如：沙丘 4K"
          prepend-inner-icon="mdi-magnify"
          hint="留空则抓取所选频道的最新消息；多个关键词用空格分隔表示需全部命中"
          persistent-hint
          clearable
          @keyup.enter="runSearch"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="selectedChannels"
          :items="channelItems"
          label="频道（可多选）"
          multiple
          chips
          closable-chips
          hint="不选 = 搜索全部已配置频道"
          persistent-hint
        />
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="limit"
          type="number"
          min="0"
          max="200"
          label="每频道上限"
          hint="0 = 用配置值"
          persistent-hint
        />
      </v-col>
      <v-col cols="6" sm="3" md="1" class="d-flex align-start">
        <v-btn block color="primary" variant="flat" :loading="loading" class="mt-1" @click="runSearch">搜索</v-btn>
      </v-col>
    </v-row>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />
    <div v-if="progressText" class="text-caption text-medium-emphasis mb-2">{{ progressText }}</div>

    <v-alert v-if="errors.length" type="warning" variant="tonal" density="compact" class="mb-3">
      <div class="font-weight-medium mb-1">部分频道搜索失败：</div>
      <ul class="panbox-search__errors">
        <li v-for="(entry, index) in errors" :key="`${entry.channel_id}-${index}`">
          <code>{{ entry.channel_id || '全部' }}</code>：{{ entry.message }}
        </li>
      </ul>
    </v-alert>

    <div v-if="searched && !loading" class="d-flex flex-wrap align-center ga-2 mb-3">
      <v-chip size="small" color="primary" variant="flat">共 {{ resultCount }} 条</v-chip>
      <v-chip size="small" variant="tonal">耗时 {{ elapsed }} ms</v-chip>
      <v-chip v-if="busyCount" size="small" color="info" variant="tonal">处理中 {{ busyCount }}</v-chip>
    </div>

    <div v-if="items.length" class="panbox-search__results">
      <ResourceCard
        v-for="item in items"
        :key="itemKey(item)"
        :item="item"
        :busy="isBusy(item)"
        :show-summary="!compact"
        @transfer="onTransfer(item, $event)"
        @favorite="onFavorite(item)"
        @copied="toast('链接已复制到剪贴板', 'success')"
        @failed="toast($event, 'error')"
      />
    </div>

    <v-alert v-else-if="searched && !loading" type="info" variant="tonal" density="compact">
      没有匹配到资源。可以尝试更换关键词，或在插件配置中补充频道。
    </v-alert>

    <v-alert v-else-if="!searched" type="info" variant="tonal" density="compact">
      输入关键词后点击「搜索」。留空关键词可直接拉取频道最新资源。
    </v-alert>

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" timeout="3000" location="top">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-search__errors {
  margin: 0;
  padding-left: 18px;
}

.panbox-search__results {
  display: flex;
  flex-direction: column;
}
</style>
