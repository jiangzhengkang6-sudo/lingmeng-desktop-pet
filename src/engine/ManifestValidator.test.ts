import { describe, expect, it } from 'vitest'
import { validateSpriteManifest } from './ManifestValidator'
import type { SpriteManifest } from '../types/pet'

function createManifest(): SpriteManifest {
  const source = (fileName: string) => ({
    src: `blob:${fileName}`, fileName, width: 128, height: 64, frameWidth: 32, frameHeight: 32,
    columns: 4, rows: 2, frameCount: 8, validFrameIndices: [0, 1, 2, 3, 4, 5, 6, 7], blankFrameIndices: [], anchor: 'bottom-center' as const,
  })
  return {
    schemaVersion: '1.0', name: 'test-sheet', version: '0.1.0', canvas: { width: 520, height: 520, background: 'transparent' },
    spriteSheets: { idle: source('idle.png'), speaking: source('speaking.png') },
    actions: {
      idle: { id: 'idle', label: '待机', sheet: 'idle', frameIndices: [0, 1], fps: 8, loop: true, interruptible: true, anchor: 'bottom-center' },
      speaking: { id: 'speaking', label: '说话', sheet: 'speaking', frameIndices: [2, 3], fps: 12, loop: true, interruptible: true, anchor: 'bottom-center' },
    },
  }
}

describe('validateSpriteManifest', () => {
  it('accepts actions bound to separate SpriteSheets', () => {
    expect(validateSpriteManifest(createManifest())).toMatchObject({ valid: true, errors: [] })
  })

  it('rejects an action that references a missing SpriteSheet', () => {
    const manifest = createManifest()
    manifest.actions.speaking!.sheet = 'missing'
    expect(validateSpriteManifest(manifest).errors).toContain('动作 speaking 引用了不存在的 SpriteSheet: missing')
  })

  it('rejects an action without a binding when multiple SpriteSheets exist', () => {
    const manifest = createManifest()
    manifest.actions.speaking!.sheet = undefined
    expect(validateSpriteManifest(manifest).errors).toContain('动作 speaking 未绑定 SpriteSheet')
  })

  it('rejects a frame that exceeds the bound SpriteSheet', () => {
    const manifest = createManifest()
    manifest.actions.speaking!.frameIndices = [7, 8]
    expect(validateSpriteManifest(manifest).errors).toContain('动作 speaking 使用了不存在的帧')
  })

  it('keeps validating legacy single-sheet manifests', () => {
    const manifest = createManifest()
    manifest.spriteSheet = manifest.spriteSheets!.idle
    manifest.spriteSheets = undefined
    manifest.actions.idle!.sheet = 'idle.png'
    delete manifest.actions.speaking
    expect(validateSpriteManifest(manifest, 8)).toMatchObject({ valid: true, errors: [] })
  })

  it('rejects invalid frame dimensions and overlapping frame markers', () => {
    const manifest = createManifest()
    manifest.spriteSheets!.idle.frameWidth = 0
    manifest.spriteSheets!.idle.blankFrameIndices = [1]
    expect(validateSpriteManifest(manifest).errors).toEqual(expect.arrayContaining(['单帧尺寸必须大于 0', '有效帧与空白帧不能重叠']))
  })
})