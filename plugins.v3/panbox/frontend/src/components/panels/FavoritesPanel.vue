<script setup>
/**
 * 收藏面板：展示 `plugin/PanBox/favorites` 列表，支持删除与一键转存。
 */
import { onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../../utils/api'
import { formatDateTime, itemTitle } from '../../utils/cloud'
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
const { busyCount, isBusy, transfer, snackbar, toast } = useResourceActions(props.api)

const loading = ref(false)
const errorText = ref('')
const records = ref([])

/**
 * 加载收藏列表。
 */
async function load() {
  loading.value = true
  errorText.value = ''
  try {
    const response = await client.favorites()
    if (response?.success === false) {
      throw new Error(readError(response, '读取收藏失败'))
    }
    records.value = Array.isArray(response?.data) ? response.data : []
  } catch (error) {
    records.value = []
    errorText.value = readError(error, '读取收藏失败')
  } finally {
    loading.value = false
  }
}

/**
 * 删除一条收藏。
 *
 * :param record: 收藏记录
 */
async function removeRecord(record) {
  try {
    const response = await client.favoriteDelete(record.id)
    if (response?.success === false) {
      throw new Error(readError(response, '删除收藏失败'))
    }
    toast('已取消收藏', 'success')
    await load()
    emit('changed')
  } catch (error) {
    toast(readError(error, '删除收藏失败'), 'error')
  }
}

/**
 * 一键转存收藏资源。
 *
 * :param record: 收藏记录
 */
async function onTransfer(record) {
  const ok = await transfer(record.item || {})
  if (ok) emit('changed')
}

onMounted(() => {
  if (props.immediate) load()
})

defineExpose({ load })
</script>

<template>
  <div class="panbox-favorites">
    <div class="d-flex align-center ga-2 mb-3">
      <v-chip size="small" color="primary" variant="flat">共 {{ records.length }} 条收藏</v-chip>
      <v-chip v-if="busyCount" size="small" color="info" variant="tonal">处理中 {{ busyCount }}</v-chip>
      <v-spacer />
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="load">
        刷新
      </v-btn>
    </div>

    <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mb-3">
      {{ errorText }}
    </v-alert>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />

    <div v-if="records.length" class="panbox-favorites__list">
      <v-card v-for="record in records" :key="record.id" variant="outlined" class="panbox-favorites__item">
        <v-card-item>
          <v-card-title class="panbox-favorites__title">{{ itemTitle(record.item) }}</v-card-title>
          <v-card-subtitle>
            收藏于 {{ formatDateTime(record.created_at) }}
            <template v-if="record.note">· 备注：{{ record.note }}</template>
          </v-card-subtitle>
        </v-card-item>
        <v-card-text class="pt-0">
          <ResourceCard
            :item="record.item || {}"
            :busy="isBusy(record.item || {})"
            :favorite-enabled="false"
            @transfer="onTransfer(record)"
            @copied="toast('链接已复制到剪贴板', 'success')"
            @failed="toast($event, 'error')"
          />
        </v-card-text>
        <v-card-actions>
          <v-btn size="small" variant="text" color="error" prepend-icon="mdi-star-off-outline" @click="removeRecord(record)">
            取消收藏
          </v-btn>
        </v-card-actions>
      </v-card>
    </div>

    <v-alert v-else-if="!loading" type="info" variant="tonal" density="compact">
      还没有收藏。在搜索结果里点击「收藏」即可把资源固定到这里。
    </v-alert>

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" timeout="3000" location="top">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-favorites__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panbox-favorites__title {
  font-size: 0.9rem;
  white-space: normal;
  word-break: break-word;
}
</style>
