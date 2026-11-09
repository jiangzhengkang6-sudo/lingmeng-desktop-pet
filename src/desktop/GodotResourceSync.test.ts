import { describe, expect, it } from 'vitest'
import { createGodotResourcePackagePayload } from './GodotResourceSync'
import type { SpriteManifest } from '../types/pet'

function createManifest(): SpriteManifest {
  return {
    schemaVersion: '1.0',
    name: 'hero',
    version: '0.1.0',
    canvas: { width: 520, height: 520, background: 'transparent' },
    spriteSheets: {
      idle: {
        src: 'data:image/png;base64,AAAA',
        fileName: 'idle.png',
        width: 64,
        height: 64,
        frameWidth: 32,
        frameHeight: 32,
        columns: 2,
        rows: 2,
        frameCount: 4,
        validFrameIndices: [0, 1],
        blankFrameIndices: [],
        anchor: 'bottom-center',
      },
    },
    actions: {
      idle: {
        id: 'idle',
        label: '待机',
        sheet: 'idle',
        frameIndices: [0, 1],
        fps: 8,
        loop: true,
        interruptible: true,
        anchor: 'bottom-center',
      },
    },
  }
}

describe('GodotResourceSync', () => {
  it('converts a resource package into a portable manifest and PNG payload', async () => {
    const payload = await createGodotResourcePackagePayload(createManifest())

    expect(payload).toMatchObject({
      manifest: {
        sprite_sheets: {
          idle: { file: 'idle.png', frame_width: 32 },
        },
      },
      images: [{ sheetKey: 'idle', dataUrl: 'data:image/png;base64,AAAA' }],
    })
  })

  it('requires at least one registered SpriteSheet', async () => {
    const manifest = createManifest()
    manifest.spriteSheets = undefined

    await expect(createGodotResourcePackagePayload(manifest))
      .rejects.toThrow('请先导入至少一张 PNG SpriteSheet')
  })
})
