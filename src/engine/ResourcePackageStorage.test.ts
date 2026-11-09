import { describe, expect, it } from 'vitest'
import { createStoredResourcePackage } from './ResourcePackageStorage'
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

describe('ResourcePackageStorage', () => {
  it('creates a versioned snapshot without sharing the manifest', () => {
    const manifest = createManifest()
    const snapshot = createStoredResourcePackage(manifest, '2026-09-04T00:00:00.000Z')

    expect(snapshot).toMatchObject({
      schemaVersion: 1,
      savedAt: '2026-09-04T00:00:00.000Z',
      manifest: { name: 'hero' },
    })
    expect(snapshot.manifest).not.toBe(manifest)

    snapshot.manifest.spriteSheets!.idle.frameWidth = 16
    expect(manifest.spriteSheets!.idle.frameWidth).toBe(32)
  })
})
