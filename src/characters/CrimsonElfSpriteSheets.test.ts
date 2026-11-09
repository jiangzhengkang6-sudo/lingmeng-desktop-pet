import { describe, expect, it } from 'vitest'
import {
  createCrimsonElfCoreActions,
  createCrimsonElfCoreSpriteSheets,
  createCrimsonElfIdleSpriteSheet,
  createCrimsonElfIdleToFrontRightAction,
  createCrimsonElfIdleToFrontRightSpriteSheet,
  createCrimsonElfThinkingSpriteSheet,
  createCrimsonElfTransitionActions,
  createCrimsonElfTransitionSpriteSheets,
  createCrimsonElfWalkActions,
  createCrimsonElfWalkSpriteSheets,
  crimsonElfThinkingSpriteSheetKey,
} from './CrimsonElfIdleSpriteSheet'

describe('crimson elf idle and transition SpriteSheets', () => {
  it('registers the 32-frame idle sheet and 16-frame front-right transition', () => {
    expect(createCrimsonElfIdleSpriteSheet()).toMatchObject({
      fileName: 'idle.png',
      width: 3840,
      height: 3840,
      frameWidth: 640,
      frameHeight: 640,
      columns: 6,
      rows: 6,
      frameCount: 36,
      blankFrameIndices: [32, 33, 34, 35],
    })
    expect(createCrimsonElfIdleToFrontRightSpriteSheet()).toMatchObject({
      fileName: 'transition-idle-to-walk-front-right.png',
      width: 2560,
      height: 2560,
      frameWidth: 640,
      frameHeight: 640,
      columns: 4,
      rows: 4,
      frameCount: 16,
    })
    expect(createCrimsonElfIdleToFrontRightAction()['transition-idle-to-walk-front-right']).toMatchObject({
      sheet: 'transition-idle-to-walk-front-right',
      frameIndices: Array.from({ length: 16 }, (_, index) => index),
      fps: 8,
      loop: false,
      interruptible: false,
    })
  })
})

describe('crimson elf core SpriteSheets', () => {
  it('registers all actions that have actual sprite resources', () => {
    const sheets = createCrimsonElfCoreSpriteSheets()
    const actions = createCrimsonElfCoreActions()
    const expectedActions = ['idle', 'listening', 'thinking', 'speaking', 'displeased', 'shy', 'open-app'] as const

    expect(Object.keys(sheets)).toEqual(expectedActions)
    for (const actionId of expectedActions) {
      expect(sheets[actionId]).toMatchObject({
        fileName: `${actionId}.png`,
        width: 3840,
        height: 3840,
        frameWidth: 640,
        frameHeight: 640,
        columns: 6,
        rows: 6,
        frameCount: 36,
        blankFrameIndices: [32, 33, 34, 35],
      })
      expect(actions[actionId]).toMatchObject({ id: actionId, sheet: actionId, fps: 8, loop: true })
    }
  })

  it('registers thinking as a 32-frame standard sheet', () => {
    const source = createCrimsonElfThinkingSpriteSheet()

    expect(crimsonElfThinkingSpriteSheetKey).toBe('thinking')
    expect(source).toMatchObject({
      width: 3840,
      height: 3840,
      frameWidth: 640,
      frameHeight: 640,
      columns: 6,
      rows: 6,
      frameCount: 36,
      blankFrameIndices: [32, 33, 34, 35],
    })
    expect(source.validFrameIndices).toEqual(Array.from({ length: 32 }, (_, index) => index))
  })
})

describe('crimson elf directional transitions', () => {
  it('registers four non-looping 16-frame idle-to-walk transitions', () => {
    const sheets = createCrimsonElfTransitionSpriteSheets()
    const actions = createCrimsonElfTransitionActions()
    const expectedActions = [
      'transition-idle-to-walk-left',
      'transition-idle-to-walk-right',
      'transition-idle-to-walk-front-left',
      'transition-idle-to-walk-front-right',
    ] as const

    expect(Object.keys(sheets)).toEqual(expectedActions)
    for (const actionId of expectedActions) {
      expect(sheets[actionId]).toMatchObject({
        fileName: `${actionId}.png`,
        width: 2560,
        height: 2560,
        frameWidth: 640,
        frameHeight: 640,
        columns: 4,
        rows: 4,
        frameCount: 16,
      })
      expect(actions[actionId]).toMatchObject({
        id: actionId,
        sheet: actionId,
        fps: 8,
        loop: false,
        interruptible: false,
      })
    }
  })
})

describe('crimson elf directional walk SpriteSheets', () => {
  it('registers six 32-frame directional walk actions', () => {
    const sheets = createCrimsonElfWalkSpriteSheets()
    const actions = createCrimsonElfWalkActions()
    const expectedActions = [
      'walk-left', 'walk-right', 'walk-front-left',
      'walk-front-right', 'walk-back-left', 'walk-back-right',
    ] as const

    expect(Object.keys(sheets)).toEqual(expectedActions)
    expect(Object.keys(actions)).toEqual(expectedActions)
    for (const actionId of expectedActions) {
      expect(sheets[actionId]).toMatchObject({
        fileName: `${actionId}.png`,
        width: 3840,
        height: 3840,
        frameWidth: 640,
        frameHeight: 640,
        columns: 6,
        rows: 6,
        frameCount: 36,
        blankFrameIndices: [32, 33, 34, 35],
      })
      expect(actions[actionId]).toMatchObject({
        id: actionId,
        sheet: actionId,
        fps: 8,
        loop: true,
      })
      expect(actions[actionId].frameIndices).toEqual(Array.from({ length: 32 }, (_, index) => index))
      expect(actions[actionId].movementFrameIndices).toEqual(Array.from({ length: 26 }, (_, index) => index + 3))
    }
  })
})

