import { ref } from 'vue'

/**
 * 轻量提示条（v-snackbar）状态封装。
 *
 * :return: 提示条状态与触发函数
 */
export function useNotifier() {
  const visible = ref(false)
  const text = ref('')
  const color = ref('success')

  /**
   * 弹出提示条。
   *
   * :param message: 提示文案
   * :param tone: success / error / warning / info
   */
  function toast(message, tone = 'success') {
    text.value = String(message || '')
    color.value = tone
    visible.value = true
  }

  return { visible, text, color, toast }
}
