<script setup>
/**
 * 历史面板：分页表格 + 关键词过滤 + 来源筛选 + 删除单条 / 清空。
 *
 * 数据来自 `plugin/PanBox/history`，删除与清空分别调用
 * `history/delete`、`history/clear`。
 */
import { computed, onMounted, ref, watch } from 'vue'

import { createPanBoxApi, readError } from '../../utils/api'
import { cloudColor, cloudLabel, formatDateTime, itemKey, itemTitle } from '../../utils/cloud'
import { useResourceActions } from '../../composables/useResourceActions'
import ResourceCard from '../common/ResourceCard.vue'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 组件挂载后是否立即加载 */
  immediate: { type: Boolean, default: true },
})

const emit = defineEmits(['changed'])

const client = createPanBoxApi(props.api)
const { busyCount, isBusy, transfer, favorite, snackbar, toast } = useResourceActions(props.api)

const loading = ref(false)
const errorText = ref('')
const records = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const source = ref('')
/** 详情展开的记录 ID */
const expanded = ref('')
const clearDialog = ref(false)

const sourceOptions = [
  { title: '全部来源', value: '' },
  { title: '搜索命中', value: 'search' },
  { title: '转存记录', value: 'transfer' },
]

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

/**
 * 来源标签文案。
 *
 * :param value: search / transfer
 * :return: 中文文案
 */
function sourceLabel(value) {
  if (value === 'search') return '搜索'
  if (value === 'transfer') return '转存'
  return value || '未知'
}

/**
 * 加载历史记录。
 */
async function load() {
  loading.value = true
  errorText.value = ''
  try {
    const response = await client.history({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim(),
      source: source.value,
    })
    if (response?.success === false) {
      throw new Error(readError(response, '读取历史失败'))
    }
    const data = response?.data || {}
    records.value = Array.isArray(data.items) ? data.items : []
    total.value = Number(data.total || 0)
    if (data.page) page.value = Number(data.page)
    if (data.page_size) pageSize.value = Number(data.page_size)
  } catch (error) {
    records.value = []
    total.value = 0
    errorText.value = readError(error, '读取历史失败')
  } finally {
    loading.value = false
  }
}

/**
 * 删除单条历史。
 *
 * :param record: 历史记录
 */
async function removeRecord(record) {
  try {
    const response = await client.historyDelete(record.id)
    if (response?.success === false) {
      throw new Error(readError(response, '删除失败'))
    }
    toast(response?.message || '已删除', 'success')
    // 当前页删空后回退一页
    if (records.value.length === 1 && page.value > 1) page.value -= 1
    await load()
    emit('changed')
  } catch (error) {
    toast(readError(error, '删除失败'), 'error')
  }
}

/**
 * 清空全部历史。
 */
async function clearAll() {
  try {
    const response = await client.historyClear()
    if (response?.success === false) {
      throw new Error(readError(response, '清空失败'))
    }
    clearDialog.value = false
    page.value = 1
    toast(response?.message || '已清空历史记录', 'success')
    await load()
    emit('changed')
  } catch (error) {
    toast(readError(error, '清空失败'), 'error')
  }
}

/**
 * 转存历史记录中的资源。
 *
 * :param record: 历史记录
 */
async function onTransfer(record) {
  const ok = await transfer(record.item || {})
  if (ok) emit('changed')
}

/**
 * 收藏历史记录中的资源。
 *
 * :param record: 历史记录
 */
function onFavorite(record) {
  favorite(record.item || {})
}

watch([page, pageSize, source], () => load())
watch(keyword, (value, oldValue) => {
  // 输入框变化时防抖：仅在清空或回车时立即查询
  if (!value || !oldValue) {
    page.value = 1
    load()
  }
})

onMounted(() => {
  if (props.immediate) load()
})
</script>

<template>
  <div class="panbox-history">
    <v-row dense>
      <v-col cols="12" sm="5">
        <v-text-field
          v-model="keyword"
          label="标题 / 正文关键词"
          prepend-inner-icon="mdi-filter-outline"
          clearable
          hide-details
          @keyup.enter="((page = 1), load())"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <v-select v-model="source" :items="sourceOptions" label="来源" hide-details />
      </v-col>
      <v-col cols="6" sm="2">
        <v-select
          v-model.number="pageSize"
          :items="[10, 20, 50, 100]"
          label="每页"
          hide-details
        />
      </v-col>
      <v-col cols="12" sm="2" class="d-flex align-center ga-1">
        <v-btn variant="tonal" color="primary" :loading="loading" prepend-icon="mdi-refresh" @click="((page = 1), load())">
          查询
        </v-btn>
        <v-btn variant="text" color="error" icon="mdi-delete-sweep-outline" title="清空历史" @click="clearDialog = true" />
      </v-col>
    </v-row>

    <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mt-3">
      {{ errorText }}
    </v-alert>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="my-3" />

    <div class="text-caption text-medium-emphasis my-3">
      共 {{ total }} 条记录，第 {{ page }} / {{ pageCount }} 页<template v-if="busyCount">，处理中 {{ busyCount }}</template>
    </div>

    <v-table v-if="records.length" density="comfortable" hover class="panbox-history__table">
      <thead>
        <tr>
          <th style="width: 150px">时间</th>
          <th style="width: 90px">来源</th>
          <th>标题</th>
          <th style="width: 170px">网盘</th>
          <th style="width: 210px">操作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="record in records" :key="record.id">
          <tr>
            <td class="text-caption">{{ formatDateTime(record.created_at) }}</td>
            <td>
              <v-chip size="x-small" variant="flat" :color="record.source === 'transfer' ? 'success' : 'primary'">
                {{ sourceLabel(record.source) }}
              </v-chip>
            </td>
            <td>
              <div class="panbox-history__title">{{ itemTitle(record.item) }}</div>
              <div v-if="record.item?.channel_name" class="text-caption text-medium-emphasis">
                {{ record.item.channel_name }}
              </div>
            </td>
            <td>
              <v-chip
                v-for="type in record.item?.cloud_types || []"
                :key="type"
                size="x-small"
                variant="tonal"
                class="mr-1 mb-1"
                :color="cloudColor(type)"
              >
                {{ cloudLabel(type) }}
              </v-chip>
            </td>
            <td>
              <v-btn
                size="small"
                variant="text"
                color="primary"
                :loading="isBusy(record.item || {})"
                @click="onTransfer(record)"
              >
                转存
              </v-btn>
              <v-btn size="small" variant="text" @click="onFavorite(record)">收藏</v-btn>
              <v-btn size="small" variant="text" @click="expanded = expanded === record.id ? '' : record.id">
                {{ expanded === record.id ? '收起' : '详情' }}
              </v-btn>
              <v-btn size="small" variant="text" color="error" @click="removeRecord(record)">删除</v-btn>
            </td>
          </tr>
          <tr v-if="expanded === record.id">
            <td colspan="5" class="pa-3">
              <ResourceCard
                :item="record.item || {}"
                :busy="isBusy(record.item || {})"
                @transfer="onTransfer(record)"
                @favorite="onFavorite(record)"
                @copied="toast('链接已复制到剪贴板', 'success')"
                @failed="toast($event, 'error')"
              />
            </td>
          </tr>
        </template>
      </tbody>
    </v-table>

    <v-alert v-else-if="!loading" type="info" variant="tonal" density="compact">
      暂无历史记录。开启「自动记录搜索与转存历史」后，搜索与转存结果会自动出现在这里。
    </v-alert>

    <div v-if="pageCount > 1" class="d-flex justify-center mt-4">
      <v-pagination v-model="page" :length="pageCount" :total-visible="7" />
    </div>

    <v-dialog v-model="clearDialog" max-width="26rem">
      <v-card>
        <v-card-title>清空历史记录</v-card-title>
        <v-card-text>将删除全部 {{ total }} 条历史记录，操作不可撤销，是否继续？</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="clearDialog = false">取消</v-btn>
          <v-btn color="error" variant="flat" @click="clearAll">确认清空</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" timeout="3000" location="top">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-history__table {
  background: transparent;
}

.panbox-history__title {
  font-size: 0.85rem;
  line-height: 1.4;
  word-break: break-word;
}
</style>
