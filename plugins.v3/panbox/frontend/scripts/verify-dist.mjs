#!/usr/bin/env node
/**
 * 构建产物校验脚本（宿主要求的硬性自检）。
 *
 * 校验目标：
 * 1. `plugins.v3/panbox/dist/assets/remoteEntry.js` 存在；
 * 2. remoteEntry.js 中引用的每个 js/css 资源都位于**同一目录**（不得出现子目录）；
 * 3. 递归检查这些资源自身的引用，确保没有悬空文件。
 *
 * 用法：`npm run verify`（`npm run build` 已串联执行）
 */
import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(here, '..', '..', 'dist', 'assets')
const entryFile = resolve(distDir, 'remoteEntry.js')

/** 资源引用正则：覆盖 import / from / new URL(..., import.meta.url) / "./x.css" 四类写法 */
const REFERENCE_PATTERNS = [
  /(?:import\s*\(\s*|from\s*|new URL\(\s*)["']([^"']+\.(?:js|css|mjs))["']/g,
  /["'](\.\/[^"']+\.(?:js|css|mjs))["']/g,
]

/**
 * 联邦容器专用兜底正则：remoteEntry.js 的样式注入清单里是裸文件名
 * （例如 `["__federation_expose_Config-xxxx.css"]`），没有 `./` 前缀。
 */
const BARE_FILENAME_PATTERN = /["']([A-Za-z0-9_][A-Za-z0-9_.@/-]*\.(?:js|css|mjs))["']/g

/**
 * 提取文本中的资源引用。
 *
 * :param text: 文件内容
 * :param allowBareFilename: 是否额外识别裸文件名（仅 remoteEntry.js 需要）
 * :return: 去重后的资源名数组
 */
function extractReferences(text, allowBareFilename = false) {
  const patterns = allowBareFilename ? [...REFERENCE_PATTERNS, BARE_FILENAME_PATTERN] : REFERENCE_PATTERNS
  const found = new Set()
  for (const pattern of patterns) {
    pattern.lastIndex = 0
    let match
    while ((match = pattern.exec(text)) !== null) {
      const value = match[1]
      if (!value || value.includes('://')) continue
      const isRelative = value.startsWith('.') || value.startsWith('/')
      const isBare = allowBareFilename && /^[A-Za-z0-9_]/.test(value)
      if (!isRelative && !isBare) continue
      found.add(value.replace(/^\.\//, ''))
    }
  }
  return [...found]
}

/**
 * 主流程：检查 remoteEntry.js 及其递归引用的全部资源。
 */
function main() {
  if (!existsSync(entryFile)) {
    console.error(`[FAIL] 未找到联邦入口：${entryFile}`)
    process.exit(1)
  }

  const queue = ['remoteEntry.js']
  const visited = new Set()
  const missing = []
  const nested = []
  const checked = []

  while (queue.length) {
    const name = queue.shift()
    if (visited.has(name)) continue
    visited.add(name)

    // 宿主按 remoteEntry.js 所在目录拼接相对资源，子目录引用会被判为不合规
    if (name.includes('/')) {
      nested.push(name)
      continue
    }

    const file = resolve(distDir, name)
    if (!existsSync(file)) {
      missing.push(name)
      continue
    }
    const size = statSync(file).size
    checked.push({ name, size })
    if (!/\.(js|mjs|css)$/.test(name)) continue
    const text = readFileSync(file, 'utf8')
    for (const reference of extractReferences(text, name === 'remoteEntry.js')) {
      if (!visited.has(reference)) queue.push(reference)
    }
  }

  console.log(`产物目录：${distDir}`)
  console.log('已确认存在的资源：')
  for (const entry of checked.sort((a, b) => a.name.localeCompare(b.name))) {
    console.log(`  - ${entry.name} (${entry.size} B)`)
  }

  const entrySize = statSync(entryFile).size
  console.log(`\nremoteEntry.js 大小：${entrySize} B`)
  console.log(`被引用的资源数量：${checked.length - 1}（不含 remoteEntry.js 自身）`)

  let failed = false
  if (nested.length) {
    console.error('\n[FAIL] 以下引用指向子目录（宿主按同目录拼接，必须平铺）：')
    for (const name of nested) console.error(`  - ${name}`)
    failed = true
  }
  if (missing.length) {
    console.error('\n[FAIL] 以下被引用的资源不存在：')
    for (const name of missing) console.error(`  - ${name}`)
    failed = true
  }
  if (failed) process.exit(1)

  console.log('\n[OK] remoteEntry.js 及其递归引用的资源全部存在，且均与其同目录（无子目录引用）。')
}

main()
