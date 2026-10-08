import { computed, ref } from 'vue'

import { createPanBoxApi, readError } from '../utils/api'
import { itemKey, p115Links } from '../utils/cloud'
import { useNotifier } from './useNotifier'

/**
 * 资源条目的通用动作（转存到 115、收藏），供搜索/历史/收藏面板复用。
 *
 * :param api: 宿主注入的 api 对象
 * :return: 动作函数与状态
 */
export function useResourceActions(api) {
  const client = createPanBoxApi(api)
  const { visible, text, color, toast } = useNotifier()
  /** 正在处理中的条目键集合 */
  const busyKeys = ref([])

  const busyCount = computed(() => busyKeys.value.length)

  /**
   * 判断条目是否正在处理中。
   *
   * :param item: ResourceItem
   * :return: 是否忙碌
   */
  function isBusy(item) {
    return busyKeys.value.includes(itemKey(item))
  }

  /**
   * 标记/取消标记条目忙碌状态。
   *
   * :param item: ResourceItem
   * :param busy: 是否忙碌
   */
  function markBusy(item, busy) {
    const key = itemKey(item)
    if (busy) {
      if (!busyKeys.value.includes(key)) busyKeys.value = [...busyKeys.value, key]
    } else {
      busyKeys.value = busyKeys.value.filter((entry) => entry !== key)
    }
  }

  /**
   * 把单条资源转存到 115 网盘。
   *
   * :param item: ResourceItem
   * :param link: 指定的 115 链接（缺省取第一条 115 链接）
   * :param cid: 目标目录 ID，缺省由后端使用配置值
   * :return: 是否全部成功
   */
  async function transfer(item, link = null, cid = '') {
    const target = link || p115Links(item)[0]
    if (!target?.url) {
      toast('该资源没有可转存的 115 链接', 'warning')
      return false
    }
    markBusy(item, true)
    try {
      const response = await client.transfer({
        url: target.url,
        receive_code: target.receive_code || '',
        cid: cid || undefined,
        channel_id: item.channel_id || '',
        channel_name: item.channel_name || '',
        message_id: item.message_id || '',
        title: item.title || '',
        content: item.content || '',
        pub_date: item.pub_date || '',
      })
      const results = Array.isArray(response?.results) ? response.results : []
      const okCount = results.filter((entry) => entry?.ok).length
      if (!results.length && response?.success === false) {
        // 整体失败（例如未启用 115、缺少 Cookie）时后端只给 message
        toast(readError(response, '转存失败'), 'error')
        return false
      }
      if (okCount === results.length && okCount > 0) {
        toast(response?.message || '转存成功', 'success')
        return true
      }
      const failed = results.find((entry) => !entry?.ok)
      toast(failed?.message || response?.message || '转存失败', 'error')
      return false
    } catch (error) {
      toast(readError(error, '转存失败'), 'error')
      return false
    } finally {
      markBusy(item, false)
    }
  }

  /**
   * 收藏单条资源。
   *
   * :param item: ResourceItem
   * :param note: 备注
   * :return: 是否收藏成功
   */
  async function favorite(item, note = '') {
    markBusy(item, true)
    try {
      const response = await client.favoriteAdd(item, note)
      if (response?.success === false) {
        toast(readError(response, '收藏失败'), 'error')
        return false
      }
      toast(response?.message || '已加入收藏', 'success')
      return true
    } catch (error) {
      toast(readError(error, '收藏失败'), 'error')
      return false
    } finally {
      markBusy(item, false)
    }
  }

  return {
    busyCount,
    isBusy,
    transfer,
    favorite,
    toast,
    // 注意：这里必须把 ref 平铺返回。模板里 `snackbar.visible` 这种「普通对象包 ref」
    // 的写法不会被自动解包（自动解包只作用于 setup 顶层绑定），会导致提示条完全不显示，
    // 因此统一由使用方在顶层解构这些 ref。
    visible,
    text,
    color,
  }
}
