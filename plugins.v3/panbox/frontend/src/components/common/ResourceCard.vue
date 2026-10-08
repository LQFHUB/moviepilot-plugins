<script setup>
/**
 * 资源条目卡片：展示标题、频道、时间、网盘标签、分享链接与提取码，
 * 并提供「复制链接 / 转存到115 / 收藏 / 打开 TG 原消息」操作。
 */
import { computed } from 'vue'

import { cloudColor, cloudLabel, formatDateTime, itemSummary, itemTitle, p115Links } from '../../utils/cloud'
import { copyText } from '../../utils/clipboard'

const props = defineProps({
  /** ResourceItem */
  item: { type: Object, required: true },
  /** 该条目是否有操作正在进行 */
  busy: { type: Boolean, default: false },
  /** 是否允许收藏 */
  favoriteEnabled: { type: Boolean, default: true },
  /** 是否展示正文摘要 */
  showSummary: { type: Boolean, default: true },
})

const emit = defineEmits(['transfer', 'favorite', 'copied', 'failed'])

const title = computed(() => itemTitle(props.item))
const summary = computed(() => (props.showSummary ? itemSummary(props.item) : ''))
const links = computed(() => props.item.cloud_links || [])
const hasP115 = computed(() => p115Links(props.item).length > 0)

/**
 * 复制单条分享链接（含提取码）。
 *
 * :param link: 网盘链接对象
 */
async function copyLink(link) {
  const text = link.receive_code ? `${link.url} 提取码：${link.receive_code}` : link.url
  const ok = await copyText(text)
  if (ok) emit('copied', link)
  else emit('failed', '复制失败，请手动选择链接复制')
}

/**
 * 复制原始消息链接。
 */
async function copyMessage() {
  const ok = await copyText(props.item.url || '')
  if (ok) emit('copied', { url: props.item.url })
  else emit('failed', '复制失败，请手动选择链接复制')
}
</script>

<template>
  <v-card class="panbox-resource" variant="tonal">
    <v-card-item>
      <v-card-title class="panbox-resource__title">{{ title }}</v-card-title>
      <v-card-subtitle class="panbox-resource__meta">
        <v-chip v-if="item.channel_name" size="x-small" color="primary" variant="flat">
          {{ item.channel_name }}
        </v-chip>
        <v-chip v-else-if="item.channel_id" size="x-small" color="primary" variant="flat">
          {{ item.channel_id }}
        </v-chip>
        <v-chip v-if="item.pub_date" size="x-small" variant="text">
          {{ formatDateTime(item.pub_date) }}
        </v-chip>
        <v-chip
          v-for="type in item.cloud_types || []"
          :key="type"
          size="x-small"
          variant="flat"
          :color="cloudColor(type)"
        >
          {{ cloudLabel(type) }}
        </v-chip>
      </v-card-subtitle>
    </v-card-item>

    <v-card-text class="pt-0">
      <p v-if="summary" class="panbox-resource__summary">{{ summary }}</p>

      <div v-for="(link, index) in links" :key="`${index}-${link.url}`" class="panbox-resource__link">
        <div class="panbox-resource__link-info">
          <v-chip size="x-small" variant="outlined" :color="cloudColor(link.cloud_type)">
            {{ cloudLabel(link.cloud_type) }}
          </v-chip>
          <span class="panbox-resource__url" :title="link.url">{{ link.url }}</span>
          <v-chip v-if="link.receive_code" size="x-small" color="warning" variant="flat">
            提取码 {{ link.receive_code }}
          </v-chip>
        </div>
        <div class="panbox-resource__link-actions">
          <v-btn size="small" variant="text" prepend-icon="mdi-content-copy" @click="copyLink(link)">
            复制链接
          </v-btn>
          <v-btn
            v-if="link.cloud_type === 'p115'"
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-cloud-upload-outline"
            :loading="busy"
            @click="emit('transfer', link)"
          >
            转存到115
          </v-btn>
        </div>
      </div>

      <v-alert v-if="!links.length" density="compact" variant="tonal" type="info" class="mt-1">
        该消息未识别到网盘分享链接
      </v-alert>
    </v-card-text>

    <v-card-actions class="panbox-resource__actions">
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-star-outline"
        :disabled="!favoriteEnabled || busy"
        @click="emit('favorite')"
      >
        收藏
      </v-btn>
      <v-btn v-if="item.url" size="small" variant="text" prepend-icon="mdi-link-variant" @click="copyMessage">
        复制消息链接
      </v-btn>
      <v-btn
        v-if="item.url"
        size="small"
        variant="text"
        prepend-icon="mdi-open-in-new"
        :href="item.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        TG 原消息
      </v-btn>
      <v-spacer />
      <v-chip v-if="item.cloud_types?.length && !hasP115" size="x-small" variant="text" color="warning">
        暂不支持该网盘转存
      </v-chip>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.panbox-resource__title {
  font-size: 0.95rem;
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}

.panbox-resource__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding-top: 4px;
  opacity: 1;
}

.panbox-resource__summary {
  margin: 0 0 8px;
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  opacity: 0.75;
}

.panbox-resource__link {
  padding: 6px 0;
  border-top: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}

.panbox-resource__link-info {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.panbox-resource__url {
  font-size: 0.78rem;
  word-break: break-all;
  opacity: 0.8;
}

.panbox-resource__link-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.panbox-resource__actions {
  flex-wrap: wrap;
}
</style>
