import testIdleSpriteSheetUrl from '../assets/testing/idle-spritesheet-test.png'
import type { SpriteSheetSource } from '../types/pet'

export const testIdleSpriteSheetKey = 'testing-idle'

export function createTestIdleSpriteSheet(): SpriteSheetSource {
  return {
    src: testIdleSpriteSheetUrl,
    fileName: 'idle-spritesheet-test.png',
    width: 3600,
    height: 3600,
    frameWidth: 720,
    frameHeight: 720,
    columns: 5,
    rows: 5,
    frameCount: 25,
    validFrameIndices: [],
    blankFrameIndices: [],
    anchor: 'bottom-center',
  }
}
