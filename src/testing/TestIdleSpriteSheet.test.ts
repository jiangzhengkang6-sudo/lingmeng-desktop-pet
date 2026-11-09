import { describe, expect, it } from 'vitest'
import { createTestIdleSpriteSheet, testIdleSpriteSheetKey } from './TestIdleSpriteSheet'

describe('test idle SpriteSheet', () => {
  it('uses the supplied testing sheet as a 25-frame idle animation', () => {
    expect(testIdleSpriteSheetKey).toBe('testing-idle')
    expect(createTestIdleSpriteSheet()).toMatchObject({
      width: 3600,
      height: 3600,
      frameWidth: 720,
      frameHeight: 720,
      columns: 5,
      rows: 5,
      frameCount: 25,
      anchor: 'bottom-center',
    })
  })
})
