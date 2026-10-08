<script setup>
/**
 * PanBox 插件配置组件（Vue 联邦暴露名 `./Config`）。
 *
 * 宿主契约（已对照 MoviePilot V3.1.1 前端 `PluginConfigDialog` 核实）：
 * - props：`initialConfig`（当前已保存配置）、`api`、`pluginId`、`sourcePluginId`、`nativeSubscribe`；
 * - emits：`save`（携带**完整**配置对象，由宿主 PUT 保存）、`layout`（`{ maxWidth }`）、`switch`、`close`。
 *
 * 排版规则（对照「网盘订阅助手」的设置面板，统一为一套字段系统）：
 * - 左侧分类导航 + 右侧内容区内部滚动，弹窗固定高度不抖动；
 * - 内容区按**分组**组织：分组标题（图标 + 标题 + 右侧说明）→ 分隔线 → 密集网格；
 * - 字段一律「标签在输入框内」（Vuetify `label`），说明走 `persistent-hint` 的 details 行，
 *   不再使用「左标签列 + 右侧控件 + 独立说明行」那种参差布局；
 * - 所有输入框强制统一 40px 高、8px 圆角，details 行固定 18px，保证纵向节奏一致；
 * - 小字号：标签/正文 13px、说明 11~12px、导航分组标题 11px。
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
  p115_enabled: false,
  p115_cookie: '',
  p115_transfer_cid: '0',
  p115_transfer_path: '',
  history_limit: 500,
  history_auto_record: true,
  auto_sync_enabled: false,
  auto_sync_cron: '0 */6 * * *',
  auto_sync_cloud_types: ['p115'],
  auto_sync_prefer_keywords: '4K,2160p,REMUX,高码',
  auto_sync_exclude_keywords: '预告,花絮,TS,枪版',
  auto_sync_min_size_gb: 0,
  auto_sync_max_size_gb: 0,
  auto_sync_max_per_run: 3,
}

/** 分类导航：分组 → 分类项 */
const NAV_GROUPS = [
  {
    name: '插件运行',
    items: [
      { value: 'basic', title: '基础设置', icon: 'mdi-tune-vertical' },
      { value: 'search', title: '搜索渠道', icon: 'mdi-magnify' },
    ],
  },
  {
    name: '网盘与订阅',
    items: [
      { value: 'drive', title: '115 网盘', icon: 'mdi-cloud-upload-outline' },
      { value: 'subscribe', title: '网盘订阅', icon: 'mdi-bell-ring-outline' },
    ],
  },
  {
    name: '数据',
    items: [{ value: 'data', title: '数据与历史', icon: 'mdi-database-outline' }],
  },
]

/** 每个分类包含的配置键，用于「有未保存修改」标记 */
const SECTION_KEYS = {
  basic: ['enabled'],
  search: ['channels', 'search_limit', 'search_filter', 'search_timeout', 'search_base_url'],
  drive: ['p115_enabled', 'p115_cookie', 'p115_transfer_cid', 'p115_transfer_path'],
  subscribe: [
    'auto_sync_enabled',
    'auto_sync_cron',
    'auto_sync_cloud_types',
    'auto_sync_prefer_keywords',
    'auto_sync_exclude_keywords',
    'auto_sync_min_size_gb',
    'auto_sync_max_size_gb',
    'auto_sync_max_per_run',
  ],
  data: ['history_limit', 'history_auto_record'],
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
  for (const key of ['enabled', 'search_filter', 'p115_enabled', 'history_auto_record', 'auto_sync_enabled']) {
    form[key] = Boolean(form[key])
  }
  form.channels = (Array.isArray(form.channels) ? form.channels : [])
    .filter((entry) => entry && typeof entry === 'object')
    .map((entry) => ({ id: String(entry.id ?? ''), name: String(entry.name ?? '') }))
  form.search_limit = Number(form.search_limit) || DEFAULT_FORM.search_limit
  form.search_timeout = Number(form.search_timeout) || DEFAULT_FORM.search_timeout
  form.history_limit = Number(form.history_limit) || DEFAULT_FORM.history_limit
  form.auto_sync_max_per_run = Number(form.auto_sync_max_per_run) || DEFAULT_FORM.auto_sync_max_per_run
  form.auto_sync_min_size_gb = Number(form.auto_sync_min_size_gb) || 0
  form.auto_sync_max_size_gb = Number(form.auto_sync_max_size_gb) || 0
  form.search_base_url = String(form.search_base_url || DEFAULT_FORM.search_base_url)
  form.p115_cookie = String(form.p115_cookie ?? '')
  form.p115_transfer_cid = String(form.p115_transfer_cid || '0')
  form.p115_transfer_path = String(form.p115_transfer_path ?? '')
  form.auto_sync_cron = String(form.auto_sync_cron || DEFAULT_FORM.auto_sync_cron)
  form.auto_sync_prefer_keywords = String(form.auto_sync_prefer_keywords ?? '')
  form.auto_sync_exclude_keywords = String(form.auto_sync_exclude_keywords ?? '')
  const types = form.auto_sync_cloud_types
  form.auto_sync_cloud_types = Array.isArray(types) && types.length ? types.map(String) : ['p115']
  return form
}

const form = reactive(normalize(props.initialConfig))
/** 已保存配置快照，用于标记「有未保存修改」的分类 */
const snapshot = ref(normalize(props.initialConfig))

const activeSection = ref('basic')
const errorText = ref('')
const checking = ref(false)
const showCookie = ref(false)
const folderDialog = ref(false)

const channelCount = computed(() => form.channels.filter((entry) => String(entry.id || '').trim()).length)
/** 115 是否已具备转存条件（开关打开且填了 Cookie） */
const is115Ready = computed(() => Boolean(form.p115_enabled) && Boolean(String(form.p115_cookie || '').trim()))
/** 自动同步是否已就绪（开启且 115 可用） */
const isAutoReady = computed(() => Boolean(form.auto_sync_enabled) && is115Ready.value)
/** 网盘类型以逗号串形式编辑 */
const cloudTypesText = computed({
  get: () => (form.auto_sync_cloud_types || []).join(','),
  set: (value) => {
    form.auto_sync_cloud_types = String(value || '')
      .split(/[,，\s]+/)
      .map((item) => item.trim())
      .filter(Boolean)
  },
})

/** 当前导航项（用于内容区标题） */
const activeNavItem = computed(() => {
  for (const group of NAV_GROUPS) {
    const hit = group.items.find((item) => item.value === activeSection.value)
    if (hit) return hit
  }
  return NAV_GROUPS[0].items[0]
})

/** 有未保存修改的分类集合 */
const dirtySections = computed(() => {
  const dirty = new Set()
  for (const [section, keys] of Object.entries(SECTION_KEYS)) {
    const current = JSON.stringify(keys.map((key) => form[key]))
    const saved = JSON.stringify(keys.map((key) => snapshot.value[key]))
    if (current !== saved) dirty.add(section)
  }
  return dirty
})

const hasUnsavedChanges = computed(() => dirtySections.value.size > 0)

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(form, normalize(value))
    snapshot.value = normalize(value)
  },
  { deep: true },
)

onMounted(() => {
  // 告知宿主对话框建议宽度：左侧导航 + 右侧两列字段需要更宽版面
  emit('layout', { maxWidth: '76rem' })
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
    p115_enabled: Boolean(form.p115_enabled),
    p115_cookie: String(form.p115_cookie || '').trim(),
    p115_transfer_cid: String(form.p115_transfer_cid || '0').trim() || '0',
    p115_transfer_path: String(form.p115_transfer_path || '').trim(),
    history_limit: Number(form.history_limit) || DEFAULT_FORM.history_limit,
    history_auto_record: Boolean(form.history_auto_record),
    auto_sync_enabled: Boolean(form.auto_sync_enabled),
    auto_sync_cron: String(form.auto_sync_cron || '').trim() || DEFAULT_FORM.auto_sync_cron,
    auto_sync_cloud_types: (form.auto_sync_cloud_types || []).length ? form.auto_sync_cloud_types : ['p115'],
    auto_sync_prefer_keywords: String(form.auto_sync_prefer_keywords || '').trim(),
    auto_sync_exclude_keywords: String(form.auto_sync_exclude_keywords || '').trim(),
    auto_sync_min_size_gb: Number(form.auto_sync_min_size_gb) || 0,
    auto_sync_max_size_gb: Number(form.auto_sync_max_size_gb) || 0,
    auto_sync_max_per_run: Number(form.auto_sync_max_per_run) || DEFAULT_FORM.auto_sync_max_per_run,
  }
}

/**
 * 校验并提交配置给宿主保存。
 */
function submit() {
  errorText.value = ''
  const payload = buildPayload()
  if (!payload.channels.length) {
    activeSection.value = 'search'
    errorText.value = '至少需要配置一个 Telegram 频道，频道 ID 为频道用户名（不含 @ 与 t.me 前缀）'
    return
  }
  if (form.auto_sync_enabled && !is115Ready.value) {
    activeSection.value = 'drive'
    errorText.value = '开启「自动同步」需要同时启用 115 并填好 Cookie，否则无法自动转存'
    return
  }
  emit('save', payload)
  snapshot.value = normalize(payload)
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
  <div class="pbx-config">
    <v-card flat class="pbx-shell">
      <!-- 顶栏：标题 + 状态 + 关闭 -->
      <header class="pbx-header">
        <v-icon icon="mdi-cloud-search-outline" size="18" class="pbx-header__icon" />
        <span class="pbx-header__title">网盘助手</span>
        <span class="pbx-chip" :class="form.enabled ? 'pbx-chip--on' : 'pbx-chip--off'">
          {{ form.enabled ? '已启用' : '已停用' }}
        </span>
        <span class="pbx-chip" :class="is115Ready ? 'pbx-chip--on' : 'pbx-chip--muted'">
          {{ is115Ready ? '115 已就绪' : '115 未就绪' }}
        </span>
        <span class="pbx-chip" :class="isAutoReady ? 'pbx-chip--on' : 'pbx-chip--muted'">
          {{ form.auto_sync_enabled ? (isAutoReady ? '自动同步开启' : '自动同步缺 115') : '自动同步关闭' }}
        </span>
        <span v-if="hasUnsavedChanges" class="pbx-chip pbx-chip--warn">有未保存修改</span>
        <v-spacer />
        <v-btn icon="mdi-close" size="x-small" variant="text" title="关闭" aria-label="关闭" @click="emit('close')" />
      </header>

      <div class="pbx-body">
        <!-- 左侧分类导航 -->
        <nav class="pbx-nav" aria-label="配置分类">
          <div v-for="group in NAV_GROUPS" :key="group.name" class="pbx-nav__group">
            <div class="pbx-nav__group-title">{{ group.name }}</div>
            <button
              v-for="item in group.items"
              :key="item.value"
              type="button"
              class="pbx-nav__item"
              :class="{ 'pbx-nav__item--active': activeSection === item.value }"
              :aria-current="activeSection === item.value ? 'true' : undefined"
              @click="activeSection = item.value"
            >
              <v-icon :icon="item.icon" size="15" class="pbx-nav__icon" />
              <span class="pbx-nav__label">{{ item.title }}</span>
              <span v-if="dirtySections.has(item.value)" class="pbx-nav__dot" title="有未保存修改" />
            </button>
          </div>

          <div class="pbx-nav__stats">
            <div class="pbx-stat">
              <span class="pbx-stat__label">频道</span>
              <span class="pbx-stat__value">{{ channelCount }}</span>
            </div>
            <div class="pbx-stat">
              <span class="pbx-stat__label">历史上限</span>
              <span class="pbx-stat__value">{{ form.history_limit }}</span>
            </div>
          </div>
        </nav>

        <!-- 右侧内容区（内部滚动） -->
        <section class="pbx-content">
          <div class="pbx-section-head">
            <v-icon :icon="activeNavItem.icon" size="15" class="pbx-section-head__icon" />
            <span class="pbx-section-head__title">{{ activeNavItem.title }}</span>
            <span v-if="dirtySections.has(activeSection)" class="pbx-section-head__dirty">未保存</span>
          </div>

          <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="pbx-alert">
            {{ errorText }}
          </v-alert>

          <!-- 基础设置 -->
          <template v-if="activeSection === 'basic'">
            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-power-plug-outline" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">运行开关</span>
                <span class="pbx-group__hint">关闭后侧栏入口与全部接口都会返回「插件未启用」</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" md="6" class="pbx-col">
                  <v-switch
                    v-model="form.enabled"
                    label="启用网盘助手插件"
                    color="primary"
                    density="compact"
                    hide-details
                  />
                </v-col>
              </v-row>
            </section>
          </template>

          <!-- 搜索渠道 -->
          <template v-else-if="activeSection === 'search'">
            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-format-list-bulleted" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">频道列表</span>
                <span class="pbx-group__hint">填频道用户名，不含 @ 与 t.me/s/ 前缀</span>
                <v-spacer />
                <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addChannel">
                  添加
                </v-btn>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-alert v-if="!form.channels.length" type="warning" variant="tonal" density="compact" class="mb-2">
                尚未配置频道，搜索将无结果。
              </v-alert>
              <div v-for="(channel, index) in form.channels" :key="index" class="pbx-channel">
                <span class="pbx-channel__index">{{ index + 1 }}</span>
                <v-text-field
                  v-model="channel.id"
                  placeholder="频道用户名，如 Quark_Movies"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
                <v-text-field
                  v-model="channel.name"
                  placeholder="显示名称（可选）"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
                <v-btn
                  icon="mdi-delete-outline"
                  variant="text"
                  color="error"
                  size="x-small"
                  :title="`删除第 ${index + 1} 个频道`"
                  :aria-label="`删除第 ${index + 1} 个频道`"
                  @click="removeChannel(index)"
                />
              </div>
            </section>

            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-tune" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">搜索行为</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" sm="6" md="4" class="pbx-col">
                  <v-text-field
                    v-model.number="form.search_limit"
                    type="number"
                    min="1"
                    max="200"
                    suffix="条"
                    label="单频道结果上限"
                    hint="单次搜索每个频道最多返回条数"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" sm="6" md="4" class="pbx-col">
                  <v-text-field
                    v-model.number="form.search_timeout"
                    type="number"
                    min="5"
                    max="120"
                    suffix="秒"
                    label="请求超时"
                    hint="抓取频道页与调用网盘接口的超时"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" md="4" class="pbx-col">
                  <v-text-field
                    v-model="form.search_base_url"
                    label="搜索基础地址"
                    hint="默认 https://t.me/s"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" class="pbx-col">
                  <v-switch
                    v-model="form.search_filter"
                    label="按关键词后置过滤"
                    color="primary"
                    density="compact"
                    hide-details="auto"
                    hint="Telegram 站内搜索是模糊匹配，开启后仅保留标题/正文含关键词的结果"
                    persistent-hint
                  />
                </v-col>
              </v-row>
            </section>
          </template>

          <!-- 115 网盘 -->
          <template v-else-if="activeSection === 'drive'">
            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-account-key-outline" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">账号</span>
                <span class="pbx-group__hint">Cookie 只保存在你的 MoviePilot 配置中</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" md="4" class="pbx-col">
                  <v-switch
                    v-model="form.p115_enabled"
                    label="启用 115 转存"
                    color="primary"
                    density="compact"
                    hide-details="auto"
                    hint="关闭时只能浏览与复制链接"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="8" class="pbx-col">
                  <div class="pbx-inline">
                    <v-text-field
                      v-model="form.p115_cookie"
                      class="pbx-grow"
                      label="115 Cookie"
                      :type="showCookie ? 'text' : 'password'"
                      :append-inner-icon="showCookie ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                      hint="浏览器登录 115 后从开发者工具复制完整 Cookie"
                      persistent-hint
                      density="compact"
                      variant="outlined"
                      autocomplete="off"
                      @click:append-inner="showCookie = !showCookie"
                    />
                    <v-btn
                      size="small"
                      variant="tonal"
                      color="primary"
                      prepend-icon="mdi-lan-connect"
                      :loading="checking"
                      @click="testCookie"
                    >
                      测试
                    </v-btn>
                  </div>
                </v-col>
              </v-row>
            </section>

            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-folder-arrow-up-down-outline" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">默认转存目标</span>
                <span class="pbx-group__hint">转存与自动同步都会落到这里</span>
                <v-spacer />
                <v-btn
                  size="x-small"
                  variant="tonal"
                  color="primary"
                  prepend-icon="mdi-folder-search-outline"
                  @click="folderDialog = true"
                >
                  选择目录
                </v-btn>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" sm="4" md="3" class="pbx-col">
                  <v-text-field
                    v-model="form.p115_transfer_cid"
                    label="目录 ID"
                    hint="0 表示根目录"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" sm="8" md="9" class="pbx-col">
                  <v-text-field
                    v-model="form.p115_transfer_path"
                    label="目录路径（备注）"
                    hint="由「选择目录」自动填充，仅用于显示"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
              </v-row>
              <v-alert v-if="!String(form.p115_cookie || '').trim()" type="info" variant="tonal" density="compact">
                未配置 Cookie 时，转存与目录浏览接口都会返回「未配置 115 Cookie」。
              </v-alert>
            </section>
          </template>

          <!-- 网盘订阅（自动同步） -->
          <template v-else-if="activeSection === 'subscribe'">
            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-sync" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">自动同步</span>
                <span class="pbx-group__hint">定时在频道里找资源并自动转存到 115</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" md="4" class="pbx-col">
                  <v-switch
                    v-model="form.auto_sync_enabled"
                    label="启用自动同步"
                    color="primary"
                    density="compact"
                    hide-details="auto"
                    :hint="is115Ready ? '按下方 cron 定时执行' : '需先启用 115 并填好 Cookie'"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" sm="6" md="4" class="pbx-col">
                  <v-text-field
                    v-model="form.auto_sync_cron"
                    label="执行周期（cron）"
                    hint="例：0 */6 * * * 表示每 6 小时"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" sm="6" md="4" class="pbx-col">
                  <v-text-field
                    v-model.number="form.auto_sync_max_per_run"
                    type="number"
                    min="1"
                    max="20"
                    suffix="个"
                    label="单次最多转存"
                    hint="每个订阅每次执行的上限"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
              </v-row>
            </section>

            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-filter-variant" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">选片规则</span>
                <span class="pbx-group__hint">体积取自 115 分享真实解析，超限不会转存</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" md="6" class="pbx-col">
                  <v-text-field
                    v-model="cloudTypesText"
                    label="允许的网盘类型"
                    hint="逗号分隔，当前驱动仅支持 p115"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" md="6" class="pbx-col">
                  <v-text-field
                    v-model="form.auto_sync_prefer_keywords"
                    label="偏好关键词"
                    hint="命中越多越优先，逗号分隔"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" md="6" class="pbx-col">
                  <v-text-field
                    v-model="form.auto_sync_exclude_keywords"
                    label="排除关键词"
                    hint="标题/正文命中即跳过，逗号分隔"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" sm="6" md="3" class="pbx-col">
                  <v-text-field
                    v-model.number="form.auto_sync_min_size_gb"
                    type="number"
                    min="0"
                    step="0.1"
                    suffix="GB"
                    label="体积下限"
                    hint="0 = 不限制"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
                <v-col cols="12" sm="6" md="3" class="pbx-col">
                  <v-text-field
                    v-model.number="form.auto_sync_max_size_gb"
                    type="number"
                    min="0"
                    step="0.1"
                    suffix="GB"
                    label="体积上限"
                    hint="0 = 不限制"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
              </v-row>
            </section>
          </template>

          <!-- 数据与历史 -->
          <template v-else-if="activeSection === 'data'">
            <section class="pbx-group">
              <div class="pbx-group__head">
                <v-icon icon="mdi-history" size="14" class="pbx-group__icon" />
                <span class="pbx-group__title">历史记录</span>
                <span class="pbx-group__hint">同一资源同来源会去重</span>
              </div>
              <v-divider class="pbx-group__divider" />
              <v-row dense class="pbx-fields">
                <v-col cols="12" md="6" class="pbx-col">
                  <v-switch
                    v-model="form.history_auto_record"
                    label="自动记录搜索与转存历史"
                    color="primary"
                    density="compact"
                    hide-details="auto"
                    hint="包含订阅自动转存的结果"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" sm="6" md="3" class="pbx-col">
                  <v-text-field
                    v-model.number="form.history_limit"
                    type="number"
                    min="10"
                    max="5000"
                    suffix="条"
                    label="历史上限"
                    hint="超出后丢弃最早记录"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                  />
                </v-col>
              </v-row>
            </section>
          </template>
        </section>
      </div>

      <!-- 底栏 -->
      <footer class="pbx-footer">
        <v-btn size="small" variant="text" prepend-icon="mdi-arrow-left" @click="emit('switch')">查看数据</v-btn>
        <v-btn size="small" variant="text" prepend-icon="mdi-close" @click="emit('close')">关闭</v-btn>
        <v-spacer />
        <span class="pbx-footer__note">由 MoviePilot 统一保存，本面板只提交变更</span>
        <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-content-save" @click="submit">
          保存配置
        </v-btn>
      </footer>
    </v-card>

    <FolderPicker v-model="folderDialog" :api="api" title="选择 115 目标目录" @select="onFolderSelected" />

    <v-snackbar v-model="visible" :color="color" timeout="3000" location="top">
      {{ text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
/* ============ 外壳：固定高度、内部滚动 ============ */
.pbx-config {
  display: flex;
  width: min(76rem, calc(100vw - 32px));
  max-width: 100%;
  min-width: 0;
  height: min(760px, calc(100dvh - 72px));
  max-height: min(760px, calc(100dvh - 72px));
  min-height: 0;
}

:global(.v-overlay__content:has(.pbx-config)) {
  overflow: hidden !important;
  border-radius: 10px !important;
}

:global(.v-overlay__content:has(.pbx-config) > *) {
  min-height: 0;
  max-height: 100%;
  overflow: hidden !important;
}

.pbx-shell {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}

/* ============ 顶栏 ============ */
.pbx-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  flex: 0 0 auto;
}

.pbx-header__icon {
  opacity: 0.75;
}

.pbx-header__title {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.2;
}

.pbx-chip {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 0.6875rem;
  line-height: 1;
  white-space: nowrap;
  border: 1px solid transparent;
}

.pbx-chip--on {
  color: rgb(var(--v-theme-success));
  background: rgba(var(--v-theme-success), 0.12);
  border-color: rgba(var(--v-theme-success), 0.3);
}

.pbx-chip--off,
.pbx-chip--muted {
  color: rgba(var(--v-theme-on-surface), 0.6);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-color: rgba(var(--v-border-color), 0.5);
}

.pbx-chip--warn {
  color: rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.12);
  border-color: rgba(var(--v-theme-warning), 0.3);
}

/* ============ 主体：左导航 + 右内容 ============ */
.pbx-body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.pbx-nav {
  display: flex;
  flex-direction: column;
  flex: 0 0 11.5rem;
  min-width: 0;
  padding: 8px;
  gap: 2px;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow-y: auto;
}

.pbx-nav__group + .pbx-nav__group {
  margin-top: 6px;
}

.pbx-nav__group-title {
  padding: 4px 8px 2px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.pbx-nav__item {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.82);
  font-size: 0.8125rem;
  line-height: 1.2;
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms ease-out, color 150ms ease-out;
}

.pbx-nav__item:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.pbx-nav__item--active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

.pbx-nav__item:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

.pbx-nav__icon {
  flex: 0 0 auto;
}

.pbx-nav__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pbx-nav__dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgb(var(--v-theme-warning));
}

.pbx-nav__stats {
  margin-top: auto;
  padding: 8px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.pbx-stat {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.pbx-stat__label {
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.pbx-stat__value {
  font-size: 0.8125rem;
  font-weight: 600;
}

/* ============ 内容区 ============ */
.pbx-content {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  padding: 10px 14px 14px;
  overflow-y: auto;
}

.pbx-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 6px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.pbx-section-head__icon {
  opacity: 0.7;
}

.pbx-section-head__title {
  font-size: 0.8125rem;
  font-weight: 600;
}

.pbx-section-head__dirty {
  margin-left: auto;
  font-size: 0.6875rem;
  color: rgb(var(--v-theme-warning));
}

.pbx-alert {
  margin-bottom: 8px;
  font-size: 0.75rem;
}

/* ---- 分组：标题行 + 分隔线 + 密集网格 ---- */
.pbx-group {
  margin-bottom: 16px;
}

.pbx-group:last-of-type {
  margin-bottom: 4px;
}

.pbx-group__head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
}

.pbx-group__icon {
  opacity: 0.65;
}

.pbx-group__title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.pbx-group__hint {
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pbx-group__divider {
  margin: 5px 0 8px;
  opacity: 0.6;
}

.pbx-fields {
  width: 100%;
  margin-inline: -4px;
}

.pbx-col {
  min-width: 0;
  margin-bottom: 6px;
}

/* 统一字段尺寸：40px 高、8px 圆角、details 行固定高度 */
.pbx-col :deep(.v-input) {
  width: 100%;
  min-width: 0;
}

.pbx-col :deep(.v-field) {
  width: 100%;
  min-width: 0;
  height: 40px !important;
  min-height: 40px !important;
  border-radius: 8px !important;
}

.pbx-col :deep(.v-field__input) {
  height: 40px !important;
  min-height: 40px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  display: flex;
  align-items: center;
  font-size: 0.8125rem;
}

.pbx-col :deep(.v-field__append-inner),
.pbx-col :deep(.v-field__prepend-inner) {
  padding-top: 0 !important;
  display: flex;
  align-items: center;
}

.pbx-col :deep(.v-input__details) {
  padding-inline: 4px;
  min-height: 18px;
}

.pbx-col :deep(.v-input__details .v-messages) {
  font-size: 0.6875rem;
}

/* 开关与字段同基线 */
.pbx-col :deep(.v-switch) {
  min-height: 40px;
  margin: 0;
  padding-inline: 4px;
}

.pbx-col :deep(.v-switch .v-label) {
  font-size: 0.8125rem;
  opacity: 1;
}

.pbx-col :deep(.v-selection-control) {
  min-height: 40px;
}

/* ---- 频道列表（内部子行） ---- */
.pbx-channel {
  display: grid;
  grid-template-columns: 1.25rem minmax(0, 1.4fr) minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  margin-bottom: 5px;
}

.pbx-channel__index {
  font-size: 0.6875rem;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-variant-numeric: tabular-nums;
}

/* ---- 行内组合（输入 + 按钮） ---- */
.pbx-inline {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}

.pbx-grow {
  flex: 1 1 14rem;
  min-width: 0;
}

/* ============ 底栏 ============ */
.pbx-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  flex: 0 0 auto;
}

.pbx-footer__note {
  font-size: 0.6875rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-right: 4px;
}

/* ============ 小屏 ============ */
@media (max-width: 720px) {
  .pbx-config {
    width: calc(100vw - 16px);
    height: min(86dvh, 760px);
    max-height: min(86dvh, 760px);
  }

  .pbx-body {
    flex-direction: column;
  }

  .pbx-nav {
    flex: 0 0 auto;
    flex-direction: row;
    gap: 4px;
    overflow-x: auto;
    padding: 6px 8px;
    border-right: 0;
    border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }

  .pbx-nav__group {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .pbx-nav__group-title,
  .pbx-nav__stats,
  .pbx-nav__dot {
    display: none;
  }

  .pbx-nav__item {
    width: auto;
    white-space: nowrap;
  }

  .pbx-channel {
    grid-template-columns: 1.25rem minmax(0, 1fr) auto;
  }

  .pbx-channel > :nth-child(3) {
    grid-column: 2 / 3;
  }

  .pbx-footer__note {
    display: none;
  }
}
</style>
