import { describe, expect, it } from 'vitest'
import { isPngFile } from './ImageFile'

describe('isPngFile', () => {
  it('accepts a PNG reported by MIME type', () => {
    expect(isPngFile({ name: 'sprite', type: 'image/png' })).toBe(true)
  })

  it('accepts a PNG file name when Windows does not provide a MIME type', () => {
    expect(isPngFile({ name: 'SpriteSheet.PNG', type: '' })).toBe(true)
  })

  it('rejects files that are neither PNG MIME types nor PNG file names', () => {
    expect(isPngFile({ name: 'sprite.jpg', type: 'image/jpeg' })).toBe(false)
  })
})
