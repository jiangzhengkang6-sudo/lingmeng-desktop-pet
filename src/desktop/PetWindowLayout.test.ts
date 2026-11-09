import { describe, expect, it } from 'vitest'
import {
  PET_WINDOW_MAX_SIZE,
  PET_WINDOW_MIN_SIZE,
  clampPetWindowSize,
  defaultPetWindowSize,
  snapPetWindowPosition,
} from './PetWindowLayout'

describe('PetWindowLayout', () => {
  it('keeps manual sizes within the supported range', () => {
    expect(clampPetWindowSize(80)).toBe(PET_WINDOW_MIN_SIZE)
    expect(clampPetWindowSize(265.7)).toBe(266)
    expect(clampPetWindowSize(600)).toBe(PET_WINDOW_MAX_SIZE)
  })

  it('derives the default size from the shorter work-area side', () => {
    expect(defaultPetWindowSize(1920, 1040)).toBe(270)
    expect(defaultPetWindowSize(320, 400)).toBe(PET_WINDOW_MIN_SIZE)
  })

  it('snaps a nearby window edge without changing the other axis', () => {
    expect(snapPetWindowPosition(
      { x: 8, y: 420 },
      { width: 240, height: 240 },
      { x: 0, y: 0, width: 1920, height: 1040 },
    )).toEqual({ x: 0, y: 420 })

    expect(snapPetWindowPosition(
      { x: 1665, y: 785 },
      { width: 240, height: 240 },
      { x: 0, y: 0, width: 1920, height: 1040 },
    )).toEqual({ x: 1680, y: 800 })
  })
})
