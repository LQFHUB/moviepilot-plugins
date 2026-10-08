<script setup>
/**
 * 115 网盘目录选择器：调用 `drive/folders` 逐级浏览目录。
 *
 * 只做只读浏览与「选中」，不负责保存配置：
 * - Config.vue 选中后写入 `p115_transfer_cid` / `p115_transfer_path` 并由宿主保存；
 * - AppPage.vue 只用于查看与复制目录 ID。
 */
import { computed, ref, watch } from 'vue'

import { createPanBoxApi, readError } from '../../utils/api'
import { copyText } from '../../utils/clipboard'
import { useNotifier } from '../../composables/useNotifier'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 对话框显隐 */
  modelValue: { type: Boolean, default: false },
  /** 对话框标题 */
  title: { type: String, default: '选择 115 目标目录' },
  /** 是否展示「选中」按钮（只读浏览时关闭） */
  selectable: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'select'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

/** 目录栈，第 0 项固定为根目录 */
const stack = ref([{ cid: '0', name: '根目录' }])
const folders = ref([])
const loading = ref(false)
const error = ref('')

const current = computed(() => stack.value[stack.value.length - 1])
const currentPath = computed(() => stack.value.map((entry) => entry.name).join(' / '))

/**
 * 加载指定目录下的子目录。
 *
 * :param cid: 目录 ID，`0` 表示根目录
 */
async function load(cid = '0') {
  loading.value = true
  error.value = ''
  try {
    const response = await client.folders(cid)
    if (response?.success === false) {
      throw new Error(readError(response, '获取目录失败'))
    }
    folders.value = Array.isArray(response?.data) ? response.data : []
  } catch (err) {
    folders.value = []
    error.value = readError(err, '获取目录失败')
  } finally {
    loading.value = false
  }
}

/**
 * 进入某个子目录。
 *
 * :param folder: `{ cid, name }`
 */
function enter(folder) {
  stack.value = [...stack.value, { cid: String(folder.cid), name: folder.name || folder.cid }]
  load(String(folder.cid))
}

/**
 * 回到目录栈中的某一级。
 *
 * :param index: 栈下标
 */
function goTo(index) {
  stack.value = stack.value.slice(0, index + 1)
  load(current.value.cid)
}

/**
 * 复制当前目录 ID。
 */
async function copyCurrent() {
  const ok = await copyText(current.value.cid)
  toast(ok ? `已复制目录 ID：${current.value.cid}` : '复制失败，请手动记录目录 ID', ok ? 'success' : 'error')
}

/**
 * 确认选中当前目录。
 */
function confirm() {
  emit('select', { cid: current.value.cid, path: currentPath.value })
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      stack.value = [{ cid: '0', name: '根目录' }]
      load('0')
    }
  },
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="52rem"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-folder-search-outline" />
        <span>{{ title }}</span>
      </v-card-title>

      <v-card-subtitle>
        当前路径：{{ currentPath }}（目录 ID：{{ current.cid }}）
      </v-card-subtitle>

      <v-divider />

      <v-card-text class="panbox-folder-picker">
        <div class="d-flex flex-wrap align-center ga-1 mb-3">
          <v-chip
            v-for="(entry, index) in stack"
            :key="entry.cid + index"
            size="small"
            :color="index === stack.length - 1 ? 'primary' : undefined"
            :variant="index === stack.length - 1 ? 'flat' : 'tonal'"
            @click="goTo(index)"
          >
            {{ entry.name }}
          </v-chip>
        </div>

        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">
          {{ error }}
        </v-alert>

        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />

        <v-list v-if="folders.length" density="comfortable" class="panbox-folder-list">
          <v-list-item v-for="folder in folders" :key="folder.cid" @click="enter(folder)">
            <template #prepend>
              <v-icon icon="mdi-folder-outline" color="warning" />
            </template>
            <v-list-item-title>{{ folder.name }}</v-list-item-title>
            <v-list-item-subtitle>ID：{{ folder.cid }}</v-list-item-subtitle>
            <template #append>
              <v-btn size="small" variant="text" prepend-icon="mdi-arrow-right" @click.stop="enter(folder)">
                进入
              </v-btn>
            </template>
          </v-list-item>
        </v-list>

        <v-alert v-else-if="!loading && !error" type="info" variant="tonal" density="compact">
          当前目录下没有子目录
        </v-alert>
      </v-card-text>

      <v-divider />

      <v-card-actions class="flex-wrap">
        <v-btn variant="text" prepend-icon="mdi-content-copy" @click="copyCurrent">复制目录 ID</v-btn>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="load(current.cid)">刷新</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">关闭</v-btn>
        <v-btn v-if="selectable" color="primary" variant="flat" @click="confirm">
          使用该目录（{{ current.cid }}）
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-snackbar v-model="visible" :color="color" timeout="2600" location="top">
      {{ text }}
    </v-snackbar>
  </v-dialog>
</template>

<style scoped>
.panbox-folder-picker {
  max-height: 60vh;
}

.panbox-folder-list {
  background: transparent;
}
</style>
