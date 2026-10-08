<script setup>
/**
 * 本地调试台（仅 `npm run dev` 使用，不参与联邦产物）。
 *
 * 宿主会在运行时注入真实的 `api` 对象，这里用一个内存 mock 替代，
 * 便于在没有 MoviePilot 宿主的情况下检查三个联邦组件的渲染与交互。
 */
import { reactive, ref } from 'vue'

import AppPage from '../components/AppPage.vue'
import Config from '../components/Config.vue'
import Page from '../components/Page.vue'

const tab = ref('app')
const logs = reactive([])

/**
 * 记录一次 mock 调用。
 *
 * :param method: 方法名
 * :param url: 请求路径
 * :param payload: 请求参数
 */
function log(method, url, payload) {
  logs.unshift({ method, url, payload: payload ? JSON.stringify(payload) : '', at: new Date().toLocaleTimeString() })
  if (logs.length > 30) logs.pop()
}

const MOCK_CHANNELS = [
  { id: 'QukanMovie', name: '115影视资源分享频道' },
  { id: 'Lsp115', name: '115网盘资源分享频道' },
]

const MOCK_ITEM = {
  channel_id: 'QukanMovie',
  channel_name: '115影视资源分享频道',
  message_id: '1024',
  title: '沙丘2 4K HDR 国语中字',
  content: '沙丘2 4K HDR 国语中字\nhttps://115cdn.com/s/swsvxg73fwl?password=i2e8 提取码：i2e8',
  pub_date: '2026-01-01T12:00:00+00:00',
  tags: ['#电影'],
  url: 'https://t.me/QukanMovie/1024',
  cloud_types: ['p115'],
  cloud_links: [
    { cloud_type: 'p115', label: '115网盘', url: 'https://115cdn.com/s/swsvxg73fwl?password=i2e8', receive_code: 'i2e8' },
  ],
}

/**
 * 解析路径结尾，模拟后端返回。
 *
 * :param url: 请求路径
 * :param config: axios 配置
 * :param method: 请求方法
 * :return: 模拟响应体
 */
async function handle(url, config, method) {
  const path = String(url).replace('plugin/PanBox/', '')
  const params = config?.params || {}
  const body = method === 'post' ? config : null
  await new Promise((resolve) => setTimeout(resolve, 120))
  if (path === 'meta') {
    return {
      success: true,
      data: {
        enabled: true,
        version: '0.1.0',
        channels: MOCK_CHANNELS,
        search_limit: 30,
        search_filter: true,
        p115: { enabled: true, configured: true, transfer_cid: '0', transfer_path: '根目录 / 影视' },
        history_count: 1,
        favorite_count: 1,
      },
    }
  }
  if (path === 'search') {
    return { success: true, items: [MOCK_ITEM], errors: [{ channel_id: 'Lsp115', message: '模拟：频道不可访问' }], count: 1, elapsed_ms: 180 }
  }
  if (path === 'transfer') {
    return { success: true, message: '转存完成：成功 1 / 共 1', results: [{ ok: true, message: '转存成功', url: MOCK_ITEM.url, file_name: '沙丘2.mkv' }] }
  }
  if (path === 'drive/folders') {
    return { success: true, data: [{ cid: '1001', name: '影视' }, { cid: '1002', name: '动画' }] }
  }
  if (path === 'drive/check') return { success: true, message: 'Cookie 有效（mock）' }
  if (path === 'history') {
    return {
      success: true,
      data: {
        items: [{ id: 'h1', created_at: Math.floor(Date.now() / 1000), source: 'search', item: MOCK_ITEM }],
        total: 1,
        page: Number(params.page || 1),
        page_size: Number(params.page_size || 20),
      },
    }
  }
  if (path === 'history/delete' || path === 'history/clear') return { success: true, message: '已处理（mock）' }
  if (path === 'favorites') {
    return { success: true, data: [{ id: 'f1', created_at: Math.floor(Date.now() / 1000), note: '想看的片', item: MOCK_ITEM }] }
  }
  if (path === 'favorites/add') return { success: true, message: '已加入收藏（mock）', data: { id: 'f2' } }
  if (path === 'favorites/delete') return { success: true, message: '已删除（mock）' }
  return { success: false, message: `mock 未实现：${path}` }
}

const mockApi = {
  get: (url, config) => {
    log('GET', url, config?.params)
    return handle(url, config, 'get')
  },
  post: (url, data) => {
    log('POST', url, data)
    return handle(url, { params: {}, data }, 'post')
  },
}
</script>

<template>
  <v-app>
    <v-app-bar color="primary" density="comfortable" flat>
      <v-app-bar-title>PanBox 本地调试台（mock api）</v-app-bar-title>
      <v-btn-toggle v-model="tab" density="comfortable" variant="tonal" divided>
        <v-btn value="app">AppPage</v-btn>
        <v-btn value="page">Page</v-btn>
        <v-btn value="config">Config</v-btn>
      </v-btn-toggle>
    </v-app-bar>

    <v-main>
      <v-container>
        <v-card class="mb-4" variant="tonal">
          <v-card-title class="text-subtitle-2">最近调用</v-card-title>
          <v-card-text class="panbox-dev__logs">
            <div v-if="!logs.length" class="text-caption">暂无调用</div>
            <div v-for="(entry, index) in logs" :key="index" class="text-caption">
              [{{ entry.at }}] {{ entry.method }} {{ entry.url }}
              <span v-if="entry.payload">· {{ entry.payload }}</span>
            </div>
          </v-card-text>
        </v-card>

        <Config
          v-if="tab === 'config'"
          :initial-config="{ enabled: true, channels: MOCK_CHANNELS, p115_cookie: 'UID=123_A1_456; CID=abc' }"
          :api="mockApi"
          plugin-id="PanBox"
          @save="(value) => logs.unshift({ method: 'EMIT', url: 'save', payload: JSON.stringify(value).slice(0, 160), at: '—' })"
          @switch="logs.unshift({ method: 'EMIT', url: 'switch', payload: '', at: '—' })"
          @close="logs.unshift({ method: 'EMIT', url: 'close', payload: '', at: '—' })"
        />

        <Page v-else-if="tab === 'page'" :api="mockApi" plugin-id="PanBox" show-switch />

        <AppPage v-else :api="mockApi" nav-key="main" plugin-id="PanBox" />
      </v-container>
    </v-main>
  </v-app>
</template>

<style scoped>
.panbox-dev__logs {
  max-height: 140px;
  overflow: auto;
  font-family: monospace;
}
</style>
