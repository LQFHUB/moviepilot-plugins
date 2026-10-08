/**
 * 海报图片地址处理。
 *
 * 背景（实例实测）：豆瓣图床对直连请求返回 **HTTP 418**（防盗链），TMDB 虽可直连但不稳定；
 * 宿主提供了同源图片代理 `GET /api/v1/system/img/{proxy}?imgurl=`（`proxy` 为布尔路径参数），
 * 由服务端代取并缓存，返回 image/webp。
 *
 * 注意：该代理需要宿主资源令牌（登录后由 Cookie 携带），因此必须使用**同源绝对路径**，
 * 不能走插件自己的 api 对象（那是 JSON 接口）。
 */

/** 图片代理前缀（与宿主默认 `API_V1_STR=/api/v1` 一致） */
export const IMAGE_PROXY_PREFIX = '/api/v1/system/img/false'

/**
 * 把远程海报地址转成宿主图片代理地址。
 *
 * :param url: 原始图片地址（通常是完整 URL）
 * :return: 可直接用于 <img src> 的地址；空值原样返回
 */
export function proxiedImage(url) {
  const text = String(url || '').trim()
  if (!text) return ''
  if (!/^https?:\/\//i.test(text)) return text
  return `${IMAGE_PROXY_PREFIX}?imgurl=${encodeURIComponent(text)}`
}
