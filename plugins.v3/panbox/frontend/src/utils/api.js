/**
 * PanBox 插件 API 访问层。
 *
 * 事实依据（对照 MoviePilot V3.1.1 宿主前端插件加载器 `federationLoader` 核实）：
 * 1. 宿主注入给 Config / Page / AppPage 的 `api` 对象，是基于 axios 的「pluginApi」实例，
 *    响应拦截器以 envelope 模式工作：**原样返回接口 JSON 响应体**，
 *    即 `{ success, message, data }` / `{ success, items, ... }` 都要自己判断 `success`；
 * 2. 该实例会自动把路径中的 `plugin/<源插件ID>` 改写成 `plugin/<实例ID>`，并自动附加
 *    Bearer Token，因此前端只写 `plugin/PanBox/xxx`，绝不接触、也不拼接任何 Token；
 * 3. 业务失败（`success: false`）不会 reject（envelope 模式），HTTP 层失败才会 reject，
 *    所以本模块统一提供 `assertOk` 与 `readError`，避免前端静默失败。
 */

/** 插件 ID（= 插件类名），路径中的固定片段 */
export const PLUGIN_ID = 'PanBox'

/**
 * 从任意异常中提取可读文案。
 *
 * :param error: 捕获到的异常（可能是 axios 错误、Error 或字符串）
 * :param fallback: 兜底文案
 * :return: 可展示给用户的中文提示
 */
export function readError(error, fallback = '请求失败，请稍后重试') {
  if (!error) return fallback
  if (typeof error === 'string') return error
  // 宿主 ApiRequestError 会带上 payload / response.data
  const payload = error.payload ?? error.response?.data
  if (payload && typeof payload === 'object') {
    for (const key of ['message', 'detail']) {
      const value = payload[key]
      if (typeof value === 'string' && value.trim()) return value
    }
  }
  if (typeof error.message === 'string' && error.message.trim()) return error.message
  return fallback
}

/**
 * 校验接口响应是否成功。
 *
 * :param response: 接口响应体
 * :param fallback: 失败时的兜底文案
 * :return: 原响应体
 * :raises Error: `success` 为 false 或响应体非法时抛出
 */
export function assertOk(response, fallback = '接口返回失败') {
  if (!response || typeof response !== 'object') {
    throw new Error(fallback)
  }
  if (response.success === false) {
    throw new Error(readError(response, fallback))
  }
  return response
}

/**
 * 创建 PanBox 插件 API 客户端。
 *
 * :param api: 宿主注入的 api 对象（可能是 pluginApi 的 Proxy）
 * :return: 各接口的调用函数集合
 */
export function createPanBoxApi(api) {
  const requireApi = () => {
    if (!api || typeof api.get !== 'function' || typeof api.post !== 'function') {
      throw new Error('未获取到宿主注入的 api 对象，无法调用插件接口')
    }
    return api
  }
  const get = (path, params) => {
    const client = requireApi()
    return client.get(`plugin/${PLUGIN_ID}/${path}`, params ? { params } : undefined)
  }
  const post = (path, body) => requireApi().post(`plugin/${PLUGIN_ID}/${path}`, body || {})
  return {
    /** 插件状态与配置摘要 */
    meta: () => get('meta'),
    /** 频道资源搜索：{ keyword, channel_id, limit, record } */
    search: (params) => get('search', params),
    /** 转存到网盘：{ url, receive_code, cid, ... } 或 { items: [...], cid } */
    transfer: (body) => post('transfer', body),
    /** 网盘目录列表：cid 默认 0（根目录） */
    folders: (cid = '0') => get('drive/folders', { cid }),
    /** 校验 Cookie 连通性；不传 cookie 时校验已保存的配置 */
    check: (cookie) => post('drive/check', cookie ? { cookie } : {}),
    /** 分页历史：{ page, page_size, keyword, source } */
    history: (params) => get('history', params),
    historyDelete: (id) => post('history/delete', { id }),
    historyClear: () => post('history/clear'),
    favorites: () => get('favorites'),
    favoriteAdd: (item, note = '') => post('favorites/add', { item, note }),
    favoriteDelete: (id) => post('favorites/delete', { id }),
    /** 榜单页签定义（复用探索的豆瓣 / TMDB 两个数据源） */
    discoverTabs: () => get('discover/tabs'),
    /** 榜单条目：{ key, sort, page, count } */
    discoverRank: (params) => get('discover/rank', params),
    /** 媒体搜索：{ keyword, media_type } */
    mediaSearch: (params) => get('media/search', params),
    /** 某标题在频道中的网盘资源（按频道分组）：{ title, media_type, season } */
    mediaResources: (params) => get('media/resources', params),
    /** 订阅列表：{ media_type } */
    subscriptions: (mediaType = '') => get('subscriptions', mediaType ? { media_type: mediaType } : undefined),
    /** 新增订阅 */
    subscriptionAdd: (payload) => post('subscriptions/add', payload),
    /** 更新订阅 */
    subscriptionUpdate: (payload) => post('subscriptions/update', payload),
    /** 删除订阅 */
    subscriptionDelete: (id) => post('subscriptions/delete', { id }),
    /** 立即执行订阅同步：{ id?, media_type? } */
    subscriptionRun: (payload = {}) => post('subscriptions/run', payload),
  }
}
