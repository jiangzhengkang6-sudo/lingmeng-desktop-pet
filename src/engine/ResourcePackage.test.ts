import { describe, expect, it } from 'vitest'
import {
  cloneManifestForTransport,
  parseActionJson,
  parseManifestJson,
  resolveSpriteSheet,
  toActionJson,
  toManifestJson,
} from './ResourcePackage'
import type { SpriteManifest } from '../types/pet'

function createSource(fileName: string, anchor: 'bottom-center' | 'center' = 'bottom-center') {
  return {
    src: `blob:${fileName}`,
    fileName,
    width: 128,
    height: 64,
    frameWidth: 32,
    frameHeight: 32,
    columns: 4,
    rows: 2,
    frameCount: 8,
    validFrameIndices: [0, 1, 2],
    blankFrameIndices: [3],
    anchor,
  }
}

function createManifest(): SpriteManifest {
  const idle = createSource('idle.png')
  const speaking = createSource('speaking.png', 'center')
  return {
    schemaVersion: '1.0',
    name: 'hero',
    version: '0.1.0',
    canvas: { width: 520, height: 520, background: 'transparent' },
    spriteSheets: { idle: idle, speaking: speaking },
    actions: {
      idle: {
        id: 'idle',
        label: '待机',
        sheet: 'idle',
        frameIndices: [0, 1, 2],
        fps: 8,
        loop: true,
        interruptible: true,
        anchor: 'bottom-center',
      },
      speaking: {
        id: 'speaking',
        label: '说话',
        sheet: 'speaking',
        frameIndices: [4, 5],
        fps: 12,
        loop: true,
        interruptible: true,
        anchor: 'center',
      },
    },
  }
}

describe('ResourcePackage', () => {
  it('serializes all registered SpriteSheets using the public snake_case schema', () => {
    const json = toManifestJson(createManifest())

    expect(json).toMatchObject({
      schema_version: '1.0',
      sprite_sheets: {
        idle: { file: 'idle.png', frame_width: 32, valid_frame_indices: [0, 1, 2] },
        speaking: { file: 'speaking.png', anchor: 'center' },
      },
      actions: {
        idle: { sheet: 'idle', frame_indices: [0, 1, 2] },
        speaking: { sheet: 'speaking', frame_indices: [4, 5] },
      },
    })
    expect(json).not.toHaveProperty('sprite_sheet')
  })

  it('parses a multi-sheet manifest and restores each action binding', () => {
    const parsed = parseManifestJson(toManifestJson(createManifest()))

    expect(parsed.manifest?.spriteSheets).toMatchObject({
      idle: { fileName: 'idle.png', frameCount: 8 },
      speaking: { fileName: 'speaking.png', anchor: 'center' },
    })
    expect(parsed.manifest?.actions.speaking).toMatchObject({ sheet: 'speaking', frameIndices: [4, 5] })
    expect(resolveSpriteSheet(parsed.manifest!, parsed.manifest!.actions.speaking)).toMatchObject({ fileName: 'speaking.png' })
  })

  it('accepts an action sheet reference by file name', () => {
    const manifest = createManifest()
    manifest.actions.speaking!.sheet = 'speaking.png'
    expect(resolveSpriteSheet(manifest, manifest.actions.speaking)).toMatchObject({ fileName: 'speaking.png' })
  })

  it('keeps parsing legacy single-sheet manifests', () => {
    const parsed = parseManifestJson({
      schema_version: '1.0',
      name: 'legacy',
      version: '0.1.0',
      canvas: { width: 520, height: 520, background: 'transparent' },
      sprite_sheet: {
        file: 'hero.png', width: 128, height: 64, frame_width: 32, frame_height: 32,
        columns: 4, rows: 2, frame_count: 8, valid_frame_indices: [0, 1], blank_frame_indices: [], anchor: 'bottom-center',
      },
      actions: { idle: { id: 'idle', label: '待机', sheet: 'hero.png', frame_indices: [0, 1], fps: 8, loop: true, interruptible: true } },
    })

    expect(parsed.manifest).toMatchObject({ spriteSheet: { fileName: 'hero.png' }, actions: { idle: { sheet: 'hero.png' } } })
  })

  it('parses a standalone action file and derives its sheet dimensions', () => {
    const parsed = parseActionJson({
      schema_version: '1.0', id: 'speaking', label: '说话', sheet: 'hero.png', frame_width: 32, frame_height: 32,
      columns: 4, rows: 2, frame_count: 8, frame_indices: [4, 5], fps: 12, loop: true, interruptible: true, anchor: 'center',
    })

    expect(parsed.action).toMatchObject({ id: 'speaking', frameIndices: [4, 5], fps: 12, anchor: 'center' })
    expect(parsed.spriteSheet).toMatchObject({ fileName: 'hero.png', width: 128, height: 64, frameCount: 8 })
  })

  it('round-trips movement frame metadata for walk actions', () => {
    const manifest = createManifest()
    manifest.actions.speaking!.movementFrameIndices = [4]
    const json = toManifestJson(manifest)

    expect(json.actions.speaking.movement_frame_indices).toEqual([4])
    const parsed = parseManifestJson(json)
    expect(parsed.manifest?.actions.speaking?.movementFrameIndices).toEqual([4])
  })

  it('rejects malformed manifest and action payloads with readable errors', () => {
    expect(() => parseManifestJson({ name: 'hero', version: '0.1.0', canvas: {}, actions: null }))
      .toThrow('manifest.json 缺少 name、version、canvas 或 actions')
    expect(() => parseActionJson({ id: 'unknown', label: '未知', frame_indices: [] }))
      .toThrow('action.json 缺少有效的 id、label 或 frame_indices')
  })

  it('round-trips a manifest without browser-only image data', () => {
    const original = createManifest()
    const parsed = parseManifestJson(toManifestJson(original))

    expect(parsed.manifest).toMatchObject({
      schemaVersion: original.schemaVersion,
      name: original.name,
      version: original.version,
      canvas: original.canvas,
      spriteSheets: {
        idle: { fileName: 'idle.png', width: 128, frameCount: 8 },
        speaking: { fileName: 'speaking.png', anchor: 'center' },
      },
      actions: original.actions,
    })
    expect(parsed.manifest?.spriteSheets?.idle).not.toHaveProperty('src')
  })

  it('round-trips a standalone action and its SpriteSheet metadata', () => {
    const original = createManifest()
    const action = { ...original.actions.speaking!, sheet: 'speaking.png' }
    const parsed = parseActionJson(toActionJson(action, original.spriteSheets!.speaking))

    expect(parsed.action).toEqual(action)
    expect(parsed.spriteSheet).toMatchObject({ fileName: 'speaking.png', frameCount: 8, anchor: 'center' })
    expect(parsed.spriteSheet).not.toHaveProperty('src')
  })

  it('clones a manifest without sharing mutable resource state', () => {
    const original = createManifest()
    const clone = cloneManifestForTransport(original)

    expect(clone).toEqual(original)
    expect(clone).not.toBe(original)
    expect(clone.spriteSheets).not.toBe(original.spriteSheets)
    expect(clone.spriteSheets!.idle).not.toBe(original.spriteSheets!.idle)

    clone.spriteSheets!.idle.frameWidth = 16
    expect(original.spriteSheets!.idle.frameWidth).toBe(32)
  })
})
