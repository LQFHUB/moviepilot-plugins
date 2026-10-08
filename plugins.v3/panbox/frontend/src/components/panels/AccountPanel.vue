<script setup>
/**
 * 账号面板（只读 + 临时校验）。
 *
 * 边界说明：
 * - Cookie、频道、默认转存目录等**持久配置**由 Config.vue 经宿主保存，
 *   本面板不调用任何写配置接口（不 PUT），避免绕过宿主的配置流程；
 * - 这里输入的 Cookie 只用于调用 `drive/check` 做即时连通性测试，不会被保存；
 * - 目录浏览调用 `drive/folders`，可逐级进入，仅用于查看 / 复制目录 ID。
 */
import { computed, onMounted, ref } from 'vue'

import { createPanBoxApi, readError } from '../../utils/api'
import { copyText } from '../../utils/clipboard'
import { useNotifier } from '../../composables/useNotifier'

const props = defineProps({
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
})

const emit = defineEmits(['action', 'meta'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

const loadingMeta = ref(false)
const metaError = ref('')
const meta = ref(null)

const cookieInput = ref('')
const showCookie = ref(false)
const checking = ref(false)

const stack = ref([{ cid: '0', name: '根目录' }])
const folders = ref([])
const loadingFolders = ref(false)
const folderError = ref('')

const p115 = computed(() => meta.value?.p115 || {})
const current = computed(() => stack.value[stack.value.length - 1])
const currentPath = computed(() => stack.value.map((entry) => entry.name).join(' / '))

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
    emit('meta', meta.value)
  } catch (error) {
    metaError.value = readError(error, '读取插件状态失败')
  } finally {
    loadingMeta.value = false
  }
}

/**
 * 加载目录列表。
 *
 * :param cid: 目录 ID
 */
async function loadFolders(cid = '0') {
  loadingFolders.value = true
  folderError.value = ''
  try {
    const response = await client.folders(cid)
    if (response?.success === false) {
      throw new Error(readError(response, '读取目录失败'))
    }
    folders.value = Array.isArray(response?.data) ? response.data : []
  } catch (error) {
    folders.value = []
    folderError.value = readError(error, '读取目录失败')
  } finally {
    loadingFolders.value = false
  }
}

/**
 * 进入子目录。
 *
 * :param folder: `{ cid, name }`
 */
function enterFolder(folder) {
  stack.value = [...stack.value, { cid: String(folder.cid), name: folder.name || folder.cid }]
  loadFolders(String(folder.cid))
}

/**
 * 返回目录栈中的某一级。
 *
 * :param index: 栈下标
 */
function goTo(index) {
  stack.value = stack.value.slice(0, index + 1)
  loadFolders(current.value.cid)
}

/**
 * 测试 Cookie 连通性（使用当前输入值，不保存）。
 */
async function testCookie() {
  checking.value = true
  try {
    const response = await client.check(cookieInput.value.trim() || undefined)
    if (response?.success === false) {
      throw new Error(readError(response, '115 Cookie 校验失败'))
    }
    toast(response?.message || '115 Cookie 可用', 'success')
  } catch (error) {
    toast(readError(error, '115 Cookie 校验失败'), 'error')
  } finally {
    checking.value = false
  }
}

/**
 * 复制目录 ID。
 */
async function copyCid() {
  const ok = await copyText(current.value.cid)
  toast(ok ? `已复制目录 ID：${current.value.cid}` : '复制失败，请手动记录目录 ID', ok ? 'success' : 'error')
}

/**
 * 请求宿主打开插件设置（多数宿主实现为空操作，仅作为扩展点）。
 */
function requestConfig() {
  emit('action', { type: 'open-plugin-config', pluginId: 'PanBox' })
  toast('请到「设置 → 插件 → 网盘助手」中修改并保存 Cookie 与默认目录', 'info')
}

onMounted(() => {
  loadMeta()
  loadFolders('0')
})
</script>

<template>
  <div class="panbox-account">
    <v-alert type="info" variant="tonal" density="compact" class="mb-4">
      本页为只读视图：Cookie、频道、默认转存目录等配置请在插件设置页保存（本页不会写入配置）。
      下面输入的 Cookie 仅用于即时连通性测试。
      <div class="mt-2">
        <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-cog-outline" @click="requestConfig">
          知道了，去设置页
        </v-btn>
      </div>
    </v-alert>

    <v-progress-linear v-if="loadingMeta" indeterminate color="primary" class="mb-3" />

    <v-alert v-if="metaError" type="error" variant="tonal" density="compact" class="mb-3">
      {{ metaError }}
    </v-alert>

    <v-card variant="outlined" class="mb-4">
      <v-card-title class="text-subtitle-2">插件状态</v-card-title>
      <v-card-text>
        <div class="d-flex flex-wrap ga-2 mb-3">
          <v-chip size="small" :color="meta?.enabled ? 'success' : 'error'" variant="flat">
            {{ meta?.enabled ? '插件已启用' : '插件未启用' }}
          </v-chip>
          <v-chip size="small" variant="tonal">版本 {{ meta?.version || '—' }}</v-chip>
          <v-chip size="small" variant="tonal">频道 {{ meta?.channels?.length || 0 }}</v-chip>
          <v-chip size="small" variant="tonal">历史 {{ meta?.history_count ?? 0 }}</v-chip>
          <v-chip size="small" variant="tonal">收藏 {{ meta?.favorite_count ?? 0 }}</v-chip>
        </div>
        <v-list density="compact" bg-color="transparent">
          <v-list-item title="115 转存" :subtitle="p115.enabled ? '已开启' : '未开启（设置页开启）'" prepend-icon="mdi-cloud-upload-outline" />
          <v-list-item
            title="115 Cookie"
            :subtitle="p115.configured ? '已配置（设置页维护）' : '未配置（设置页维护）'"
            prepend-icon="mdi-key-outline"
          />
          <v-list-item
            title="默认转存目录"
            :subtitle="`${p115.transfer_path || '未命名'}（ID：${p115.transfer_cid || '0'}）`"
            prepend-icon="mdi-folder-outline"
          />
        </v-list>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" class="mb-4">
      <v-card-title class="text-subtitle-2">115 Cookie 连通性测试</v-card-title>
      <v-card-text>
        <div class="d-flex flex-wrap align-start ga-2">
          <v-text-field
            v-model="cookieInput"
            class="flex-grow-1"
            label="临时 Cookie（不会保存）"
            :type="showCookie ? 'text' : 'password'"
            :append-inner-icon="showCookie ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            hint="留空表示校验已保存的 Cookie；填入则校验本次输入值"
            persistent-hint
            autocomplete="off"
            @click:append-inner="showCookie = !showCookie"
          />
          <v-btn
            class="mt-1"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-lan-connect"
            :loading="checking"
            @click="testCookie"
          >
            测试连通性
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <v-card variant="outlined">
      <v-card-title class="text-subtitle-2">目录浏览（drive/folders）</v-card-title>
      <v-card-subtitle>当前路径：{{ currentPath }}（ID：{{ current.cid }}）</v-card-subtitle>
      <v-card-text>
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
          <v-spacer />
          <v-btn size="small" variant="text" prepend-icon="mdi-content-copy" @click="copyCid">复制当前目录 ID</v-btn>
          <v-btn size="small" variant="text" prepend-icon="mdi-refresh" :loading="loadingFolders" @click="loadFolders(current.cid)">
            刷新
          </v-btn>
        </div>

        <v-alert v-if="folderError" type="error" variant="tonal" density="compact" class="mb-3">
          {{ folderError }}
          <div class="text-caption mt-1">若提示未配置 Cookie，请先到插件设置页填写并保存 115 Cookie。</div>
        </v-alert>

        <v-progress-linear v-if="loadingFolders" indeterminate color="primary" class="mb-3" />

        <v-list v-if="folders.length" density="comfortable" bg-color="transparent">
          <v-list-item v-for="folder in folders" :key="folder.cid" @click="enterFolder(folder)">
            <template #prepend>
              <v-icon icon="mdi-folder-outline" color="warning" />
            </template>
            <v-list-item-title>{{ folder.name }}</v-list-item-title>
            <v-list-item-subtitle>ID：{{ folder.cid }}</v-list-item-subtitle>
            <template #append>
              <v-btn size="small" variant="text" prepend-icon="mdi-arrow-right" @click.stop="enterFolder(folder)">进入</v-btn>
            </template>
          </v-list-item>
        </v-list>

        <v-alert v-else-if="!loadingFolders && !folderError" type="info" variant="tonal" density="compact">
          当前目录下没有子目录。
        </v-alert>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">
      {{ text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-account {
  padding-bottom: 8px;
}
</style>
