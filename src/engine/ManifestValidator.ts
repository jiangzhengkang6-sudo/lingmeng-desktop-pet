import { resolveSpriteSheet } from './ResourcePackage'
import type { SpriteManifest, SpriteAnchor, SpriteSheetSource } from '../types/pet'

export type ManifestValidation = {
  valid: boolean
  errors: string[]
  warnings: string[]
}

const anchors: SpriteAnchor[] = ['bottom-center', 'center']

export function validateSpriteManifest(
  manifest: SpriteManifest,
  availableFrameCount?: number,
): ManifestValidation {
  const errors: string[] = []
  const warnings: string[] = []

  if (!manifest.schemaVersion.trim()) errors.push('清单版本不能为空')
  if (!manifest.name.trim()) errors.push('资源名称不能为空')
  if (!manifest.version.trim()) errors.push('资源版本不能为空')
  if (manifest.canvas.width <= 0 || manifest.canvas.height <= 0) {
    errors.push('画布尺寸必须大于 0')
  }

  const sources = Object.entries(manifest.spriteSheets ?? {})
  if (sources.length === 0 && manifest.spriteSheet) sources.push(['default', manifest.spriteSheet])
  for (const [, source] of sources) validateSource(source, errors, warnings)

  const entries = Object.entries(manifest.actions)
  if (entries.length === 0) errors.push('至少需要配置一个动作')

  for (const [key, action] of entries) {
    if (!action) {
      errors.push(`动作 ${key} 缺少定义`)
      continue
    }
    if (action.id !== key) errors.push(`动作 ${key} 的 id 不匹配`)
    if (action.frameIndices.length === 0) {
      errors.push(`动作 ${key} 没有可播放帧`)
      continue
    }
    if (action.fps <= 0) errors.push(`动作 ${key} 的 FPS 必须大于 0`)
    if (!anchors.includes(action.anchor)) errors.push(`动作 ${key} 的锚点无效`)
    if (action.frameIndices.some((frame) => !Number.isInteger(frame) || frame < 0)) {
      errors.push(`动作 ${key} 包含无效帧编号`)
    }

    const source = resolveSpriteSheet(manifest, action)
    if (sources.length > 0 && action.sheet && !source) {
      errors.push(`动作 ${key} 引用了不存在的 SpriteSheet: ${action.sheet}`)
      continue
    }
    if (sources.length > 1 && !action.sheet) {
      errors.push(`动作 ${key} 未绑定 SpriteSheet`)
      continue
    }
    if (availableFrameCount !== undefined && action.frameIndices.some((frame) => frame >= availableFrameCount)) {
      errors.push(`动作 ${key} 使用了不存在的帧`)
    }
    if (source && action.frameIndices.some((frame) => source.blankFrameIndices.includes(frame))) {
      errors.push(`动作 ${key} 使用了空白帧`)
    }
    if (source && source.validFrameIndices.length > 0 && action.frameIndices.some((frame) => !source.validFrameIndices.includes(frame))) {
      errors.push(`动作 ${key} 使用了未标记为有效的帧`)
    }
    if (source && action.frameIndices.some((frame) => frame >= source.frameCount)) {
      errors.push(`动作 ${key} 使用了不存在的帧`)
    }
  }

  if (!manifest.actions.idle) warnings.push('未配置 idle，播放时会回退到占位待机动作')

  return { valid: errors.length === 0, errors, warnings }
}

function validateSource(source: SpriteSheetSource, errors: string[], warnings: string[]) {
  if (source.frameWidth <= 0 || source.frameHeight <= 0) {
    errors.push('单帧尺寸必须大于 0')
  }
  if (source.frameWidth > source.width || source.frameHeight > source.height) {
    errors.push('单帧尺寸不能超过图片尺寸')
  }
  if (source.columns <= 0 || source.rows <= 0 || source.frameCount <= 0) {
    errors.push('SpriteSheet 网格尺寸无效')
  }
  if (source.frameCount > source.columns * source.rows) {
    errors.push('有效帧数量不能超过 SpriteSheet 网格总数')
  }
  if (!anchors.includes(source.anchor)) errors.push('SpriteSheet 锚点无效')
  if (source.frameWidth > 0 && source.frameHeight > 0
    && (source.width % source.frameWidth !== 0 || source.height % source.frameHeight !== 0)) {
    warnings.push('图片边缘存在未使用的像素')
  }
  if (source.validFrameIndices.some((frame) => frame < 0 || frame >= source.frameCount)) {
    errors.push('有效帧列表包含不存在的帧')
  }
  if (source.blankFrameIndices.some((frame) => frame < 0 || frame >= source.frameCount)) {
    errors.push('空白帧列表包含不存在的帧')
  }
  if (source.validFrameIndices.some((frame) => source.blankFrameIndices.includes(frame))) {
    errors.push('有效帧与空白帧不能重叠')
  }
}