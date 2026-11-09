import { describe, expect, it } from 'vitest'
import { parseFrameList } from './FrameList'

describe('parseFrameList', () => {
  it('treats an empty editor field as an empty frame list', () => {
    expect(parseFrameList('')).toEqual([])
    expect(parseFrameList('   ')).toEqual([])
  })

  it('keeps unique non-negative integer frame indices', () => {
    expect(parseFrameList('0, 2，2 5 -1 1.5')).toEqual([0, 2, 5])
  })
})