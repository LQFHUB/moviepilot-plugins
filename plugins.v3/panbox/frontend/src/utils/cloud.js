/**
 * 网盘类型与时间展示工具。
 *
 * 网盘代号与后端 `core/models.py` 的 `CLOUD_LABELS` 保持一致，
 * 前端保留一份用于打标签，避免为了展示再发一次请求。
 */

/** 网盘代号 → 中文名称 */
export const CLOUD_LABELS = {
  p115: '115网盘',
  quark: '夸克网盘',
  aliyun: '阿里云盘',
  tianyi: '天翼云盘',
  p123: '123网盘',
  baidu: '百度网盘',
  yun139: '移动云盘',
}

/** 网盘代号 → Vuetify 芯片配色 */
export const CLOUD_COLORS = {
  p115: 'primary',
  quark: 'purple',
  aliyun: 'indigo',
  tianyi: 'teal',
  p123: 'orange',
  baidu: 'blue',
  yun139: 'green',
}

/**
 * 取得网盘中文名。
 *
 * :param type: 网盘代号
 * :return: 中文名称，未知代号原样返回
 */
export function cloudLabel(type) {
  if (!type) return '未知网盘'
  return CLOUD_LABELS[type] || String(type)
}

/**
 * 取得网盘芯片配色。
 *
 * :param type: 网盘代号
 * :return: Vuetify 颜色名
 */
export function cloudColor(type) {
  return CLOUD_COLORS[type] || 'grey'
}

/**
 * 统一格式化时间：历史记录用秒级时间戳，搜索结果用字符串时间。
 *
 * :param value: 秒/毫秒时间戳或时间字符串
 * :return: `YYYY-MM-DD HH:mm` 形式的文本
 */
export function formatDateTime(value) {
  if (value === null || value === undefined || value === '') return '—'
  let date
  const text = String(value)
  if (/^\d+$/.test(text)) {
    const num = Number(text)
    date = new Date(num < 1e12 ? num * 1000 : num)
  } else {
    date = new Date(text)
  }
  if (Number.isNaN(date.getTime())) return text
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 过滤出资源条目里的 115 分享链接。
 *
 * :param item: ResourceItem
 * :return: 115 链接数组
 */
export function p115Links(item) {
  return (item?.cloud_links || []).filter((link) => link && link.cloud_type === 'p115' && link.url)
}

/**
 * 资源条目标题：优先标题，其次正文首行，最后回落到频道消息链接。
 *
 * :param item: ResourceItem
 * :return: 展示用标题
 */
export function itemTitle(item) {
  const title = String(item?.title || '').trim()
  if (title) return title
  const content = String(item?.content || '').trim()
  if (content) return content.split('\n')[0]
  return item?.url || '未命名资源'
}

/**
 * 资源条目摘要正文（去掉标题占据的首行）。
 *
 * :param item: ResourceItem
 * :param max: 最大字符数
 * :return: 摘要文本
 */
export function itemSummary(item, max = 160) {
  const title = String(item?.title || '').trim()
  let content = String(item?.content || '').trim()
  if (title && content.startsWith(title)) {
    content = content.slice(title.length).trim()
  }
  if (content.length <= max) return content
  return `${content.slice(0, max)}…`
}

/**
 * 资源条目去重键（频道 + 消息 ID）。
 *
 * :param item: ResourceItem
 * :return: 去重键
 */
export function itemKey(item) {
  return `${item?.channel_id || ''}:${item?.message_id || ''}:${item?.url || ''}`
}
