import { describe, expect, it } from 'vitest'
import { calculateSpriteSheetGeometry } from './SpriteSheetGeometry'

describe('calculateSpriteSheetGeometry', () => {
  it('recalculates a 3600px square sheet into a 5 by 5 frame grid', () => {
    expect(calculateSpriteSheetGeometry(3600, 3600, 720, 720)).toEqual({
      columns: 5,
      rows: 5,
      frameCount: 25,
    })
  })

  it('returns an empty grid for an invalid frame size', () => {
    expect(calculateSpriteSheetGeometry(3600, 3600, 0, 720)).toEqual({
      columns: 0,
      rows: 0,
      frameCount: 0,
    })
  })
})
