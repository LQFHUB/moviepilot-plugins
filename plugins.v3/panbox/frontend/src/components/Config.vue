<script setup>
/**
 * PanBox 插件配置组件（Vue 联邦暴露名 `./Config`）。
 *
 * 宿主契约（已对照 MoviePilot V3.1.1 前端 `PluginConfigDialog` 核实）：
 * - props：`initialConfig`（当前已保存配置）、`api`、`pluginId`、`sourcePluginId`、`nativeSubscribe`；
 * - emits：`save`（携带**完整**配置对象，由宿主 PUT 保存）、`layout`（`{ maxWidth }`）、`switch`、`close`。
 *
 * 本组件**不**自行保存配置，也不接触任何 Token：所有网络请求都走宿主注入的 api 对象。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { useNotifier } from '../composables/useNotifier'
import FolderPicker from './common/FolderPicker.vue'

const props = defineProps({
  /** 宿主传入的当前配置（可能包含已保存的 115 Cookie） */
  initialConfig: { type: Object, default: () => ({}) },
  /** 宿主注入的 api 对象 */
  api: { type: Object, default: null },
  /** 插件实例 ID */
  pluginId: { type: String, default: '' },
  /** 插件源 ID */
  sourcePluginId: { type: String, default: '' },
  /** 宿主原生订阅能力（本插件未使用，保留契约） */
  nativeSubscribe: { type: Object, default: null },
})

const emit = defineEmits(['save', 'layout', 'switch', 'close'])

const client = createPanBoxApi(props.api)
const { visible, text, color, toast } = useNotifier()

/** 表单默认值，键名与后端 `core/config.py::DEFAULT_CONFIG` 完全一致 */
const DEFAULT_FORM = {
  enabled: false,
  channels: [],
  search_limit: 30,
  search_timeout: 20,
  search_filter: true,
  search_base_url: 'https://t.me/s',
  search_proxy: '',
  p115_enabled: false,
  p115_cookie: '',
  p115_transfer_cid: '0',
  p115_transfer_path: '',
  history_limit: 500,
  history_auto_record: true,
}

/**
 * 把宿主配置规范化成表单模型（补齐缺失键、统一类型）。
 *
 * :param raw: 宿主传入的配置
 * :return: 表单模型
 */
function normalize(raw) {
  const source = raw && typeof raw === 'object' ? raw : {}
  const form = { ...DEFAULT_FORM, ...source }
  form.enabled = Boolean(form.enabled)
  form.search_filter = Boolean(form.search_filter)
  form.p115_enabled = Boolean(form.p115_enabled)
  form.history_auto_record = Boolean(form.history_auto_record)
  form.channels = (Array.isArray(form.channels) ? form.channels : [])
    .filter((entry) => entry && typeof entry === 'object')
    .map((entry) => ({ id: String(entry.id ?? ''), name: String(entry.name ?? '') }))
  form.search_limit = Number(form.search_limit) || DEFAULT_FORM.search_limit
  form.search_timeout = Number(form.search_timeout) || DEFAULT_FORM.search_timeout
  form.history_limit = Number(form.history_limit) || DEFAULT_FORM.history_limit
  form.search_base_url = String(form.search_base_url || DEFAULT_FORM.search_base_url)
  form.search_proxy = String(form.search_proxy ?? '')
  form.p115_cookie = String(form.p115_cookie ?? '')
  form.p115_transfer_cid = String(form.p115_transfer_cid || '0')
  form.p115_transfer_path = String(form.p115_transfer_path ?? '')
  return form
}

const form = reactive(normalize(props.initialConfig))
/** 默认展开的面板下标 */
const openPanels = ref([0, 1])
const errorText = ref('')
const checking = ref(false)
const showCookie = ref(false)
const folderDialog = ref(false)

const channelCount = computed(() => form.channels.filter((entry) => String(entry.id || '').trim()).length)

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(form, normalize(value))
  },
  { deep: true },
)

onMounted(() => {
  // 告知宿主对话框建议宽度
  emit('layout', { maxWidth: '72rem' })
})

/**
 * 新增一行频道。
 */
function addChannel() {
  form.channels.push({ id: '', name: '' })
}

/**
 * 删除一行频道。
 *
 * :param index: 行下标
 */
function removeChannel(index) {
  form.channels.splice(index, 1)
}

/**
 * 生成待提交的完整配置对象。
 *
 * :return: 配置对象
 */
function buildPayload() {
  return {
    enabled: Boolean(form.enabled),
    channels: form.channels
      .map((entry) => ({ id: String(entry.id || '').trim().replace(/^@/, ''), name: String(entry.name || '').trim() }))
      .filter((entry) => entry.id),
    search_limit: Number(form.search_limit) || DEFAULT_FORM.search_limit,
    search_timeout: Number(form.search_timeout) || DEFAULT_FORM.search_timeout,
    search_filter: Boolean(form.search_filter),
    search_base_url: String(form.search_base_url || '').trim() || DEFAULT_FORM.search_base_url,
    search_proxy: String(form.search_proxy || '').trim(),
    p115_enabled: Boolean(form.p115_enabled),
    p115_cookie: String(form.p115_cookie || '').trim(),
    p115_transfer_cid: String(form.p115_transfer_cid || '0').trim() || '0',
    p115_transfer_path: String(form.p115_transfer_path || '').trim(),
    history_limit: Number(form.history_limit) || DEFAULT_FORM.history_limit,
    history_auto_record: Boolean(form.history_auto_record),
  }
}

/**
 * 校验并提交配置给宿主保存。
 */
function submit() {
  errorText.value = ''
  const payload = buildPayload()
  if (!payload.channels.length) {
    errorText.value = '至少需要配置一个 Telegram 频道，频道 ID 为频道用户名（不含 @ 与 t.me 前缀）'
    return
  }
  emit('save', payload)
  toast('配置已提交，由 MoviePilot 保存', 'success')
}

/**
 * 测试 115 Cookie 连通性（当前输入值，不落盘）。
 */
async function testCookie() {
  const cookie = String(form.p115_cookie || '').trim()
  checking.value = true
  try {
    const response = await client.check(cookie)
    if (response?.success === false) {
      throw new Error(readError(response, '115 Cookie 校验失败'))
    }
    toast(response?.message || '115 Cookie 可用', 'success')
  } catch (err) {
    toast(readError(err, '115 Cookie 校验失败'), 'error')
  } finally {
    checking.value = false
  }
}

/**
 * 处理目录选择结果。
 *
 * :param payload: `{ cid, path }`
 */
function onFolderSelected(payload) {
  form.p115_transfer_cid = String(payload?.cid || '0')
  if (payload?.path) form.p115_transfer_path = payload.path
  toast(`已选择目录：${form.p115_transfer_path || form.p115_transfer_cid}`, 'success')
}
</script>

<template>
  <div class="panbox-config">
    <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mb-3">
      {{ errorText }}
    </v-alert>

    <v-expansion-panels v-model="openPanels" variant="accordion" multiple>
      <!-- 基础与搜索 -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <v-icon icon="mdi-magnify" class="mr-2" />频道搜索
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-switch v-model="form.enabled" color="primary" label="启用插件" hide-details class="mb-1" />
          <div class="text-caption text-medium-emphasis mb-4">
            关闭后侧栏入口与全部接口都会返回「插件未启用」。
          </div>

          <v-row dense>
            <v-col cols="12" sm="6" md="4">
              <v-text-field
                v-model.number="form.search_limit"
                type="number"
                min="1"
                max="200"
                label="每频道结果上限"
                hint="单次搜索每个频道最多返回的条数"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <v-text-field
                v-model.number="form.search_timeout"
                type="number"
                min="5"
                max="120"
                label="请求超时（秒）"
                hint="抓取 t.me 预览页与调用网盘接口的超时时间"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <v-text-field
                v-model="form.history_limit"
                type="number"
                min="10"
                max="5000"
                label="历史记录上限"
                hint="超出后自动丢弃最早的记录"
                persistent-hint
              />
            </v-col>
          </v-row>

          <v-switch
            v-model="form.search_filter"
            color="primary"
            label="按关键词后置过滤"
            hint="Telegram 站内搜索为模糊匹配，开启后仅保留正文/标题包含关键词的结果"
            persistent-hint
            class="mt-3"
          />
          <v-switch
            v-model="form.history_auto_record"
            color="primary"
            label="自动记录搜索与转存历史"
            hide-details
            class="mb-3"
          />

          <v-text-field
            v-model="form.search_base_url"
            label="搜索基础地址"
            hint="默认 https://t.me/s，仅在官方预览页失效时调整"
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model="form.search_proxy"
            label="网络代理（可选）"
            placeholder="http://127.0.0.1:7890"
            hint="留空表示不使用代理；由插件后端发起请求"
            persistent-hint
          />

          <v-divider class="my-5" />

          <div class="d-flex align-center ga-2 mb-1">
            <span class="text-subtitle-2">频道列表（{{ channelCount }} 个）</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addChannel">
              添加频道
            </v-btn>
          </div>
          <div class="text-caption text-medium-emphasis mb-3">
            频道 ID 填 Telegram 频道用户名，不带 <code>@</code> 与 <code>t.me/s/</code> 前缀，例如
            <code>moviepilot_channel</code>；名称仅用于界面展示。
          </div>

          <v-alert v-if="!form.channels.length" type="warning" variant="tonal" density="compact" class="mb-2">
            尚未配置频道，搜索将无结果。
          </v-alert>

          <div v-for="(channel, index) in form.channels" :key="index" class="panbox-config__channel">
            <v-text-field
              v-model="channel.id"
              label="频道用户名"
              placeholder="moviepilot_channel"
              density="comfortable"
              hide-details
            />
            <v-text-field
              v-model="channel.name"
              label="显示名称"
              placeholder="影视资源分享"
              density="comfortable"
              hide-details
            />
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              color="error"
              size="small"
              :title="`删除第 ${index + 1} 个频道`"
              @click="removeChannel(index)"
            />
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>

      <!-- 115 账号 -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <v-icon icon="mdi-cloud-upload-outline" class="mr-2" />115 网盘
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-switch
            v-model="form.p115_enabled"
            color="primary"
            label="启用 115 网盘转存"
            hide-details
            class="mb-3"
          />

          <div class="d-flex flex-wrap align-start ga-2">
            <v-text-field
              v-model="form.p115_cookie"
              class="flex-grow-1"
              label="115 Cookie"
              :type="showCookie ? 'text' : 'password'"
              :append-inner-icon="showCookie ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
              hint="浏览器登录 115 后复制完整 Cookie；仅在本地保存，不会发送到第三方"
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

          <v-divider class="my-5" />

          <div class="d-flex flex-wrap align-center ga-2 mb-1">
            <span class="text-subtitle-2">默认转存目录</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-folder-search-outline" @click="folderDialog = true">
              选择目录
            </v-btn>
          </div>
          <v-row dense class="mt-1">
            <v-col cols="12" sm="5">
              <v-text-field
                v-model="form.p115_transfer_cid"
                label="目标目录 ID"
                placeholder="0"
                hint="0 表示根目录"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" sm="7">
              <v-text-field
                v-model="form.p115_transfer_path"
                label="目标目录路径（备注）"
                hint="由「选择目录」自动填充，仅用于显示；实际目录以目录 ID 为准"
                persistent-hint
              />
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis mt-3">
            未配置 Cookie 时，转存与目录浏览接口都会返回「未配置 115 Cookie」。
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-card-actions class="px-0 mt-4 flex-wrap">
      <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="emit('switch')">查看数据</v-btn>
      <v-btn variant="text" prepend-icon="mdi-close" @click="emit('close')">关闭</v-btn>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-content-save" @click="submit">保存配置</v-btn>
    </v-card-actions>

    <div class="text-caption text-medium-emphasis">
      配置由 MoviePilot 统一保存（本组件只 emit <code>save</code>，不直接写接口）。
    </div>

    <FolderPicker v-model="folderDialog" :api="api" title="选择 115 目标目录" @select="onFolderSelected" />

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">
      {{ text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.panbox-config {
  padding: 8px 16px 16px;
}

.panbox-config__channel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

@media (max-width: 600px) {
  .panbox-config__channel {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
</style>
