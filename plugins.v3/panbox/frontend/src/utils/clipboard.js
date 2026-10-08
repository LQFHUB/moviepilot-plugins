/**
 * 剪贴板工具：优先使用异步 Clipboard API，失败时降级到 execCommand。
 */

/**
 * 复制文本到剪贴板。
 *
 * :param text: 待复制文本
 * :return: 是否复制成功
 */
export async function copyText(text) {
  const value = String(text ?? '')
  if (!value) return false
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
      return true
    }
  } catch {
    // 非安全上下文或权限被拒时继续走降级方案
  }
  try {
    const area = document.createElement('textarea')
    area.value = value
    area.setAttribute('readonly', 'readonly')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
