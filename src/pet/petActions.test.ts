import { describe, expect, it } from 'vitest'
import { availablePetActions, isAvailablePetAction, normalizePetAction } from './petActions'

describe('pet action normalization', () => {
  it('keeps actions that have actual resources', () => {
    for (const action of availablePetActions) {
      expect(normalizePetAction(action)).toBe(action)
      expect(isAvailablePetAction(action)).toBe(true)
    }
  })

  it('maps legacy event actions to available animations', () => {
    expect(normalizePetAction('success')).toBe('open-app')
    expect(normalizePetAction('working')).toBe('open-app')
    expect(normalizePetAction('failure')).toBe('displeased')
    expect(normalizePetAction('refuse')).toBe('displeased')
    expect(normalizePetAction('sleeping')).toBe('idle')
    expect(normalizePetAction('reminder')).toBe('idle')
  })

  it('falls back to idle for unknown or empty actions', () => {
    expect(normalizePetAction('dance')).toBe('idle')
    expect(normalizePetAction('')).toBe('idle')
    expect(normalizePetAction(null)).toBe('idle')
    expect(normalizePetAction(undefined)).toBe('idle')
    expect(isAvailablePetAction('success')).toBe(false)
  })
})
