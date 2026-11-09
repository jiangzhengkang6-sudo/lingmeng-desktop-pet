import idleUrl from '../assets/characters/crimson-elf/sprites/idle.png'
import listeningUrl from '../assets/characters/crimson-elf/sprites/listening.png'
import thinkingUrl from '../assets/characters/crimson-elf/sprites/thinking.png'
import speakingUrl from '../assets/characters/crimson-elf/sprites/speaking.png'
import displeasedUrl from '../assets/characters/crimson-elf/sprites/displeased.png'
import shyUrl from '../assets/characters/crimson-elf/sprites/shy.png'
import openAppUrl from '../assets/characters/crimson-elf/sprites/open-app.png'
import walkLeftUrl from '../assets/characters/crimson-elf/sprites/walk-left.png'
import walkRightUrl from '../assets/characters/crimson-elf/sprites/walk-right.png'
import walkFrontLeftUrl from '../assets/characters/crimson-elf/sprites/walk-front-left.png'
import walkFrontRightUrl from '../assets/characters/crimson-elf/sprites/walk-front-right.png'
import walkBackLeftUrl from '../assets/characters/crimson-elf/sprites/walk-back-left.png'
import walkBackRightUrl from '../assets/characters/crimson-elf/sprites/walk-back-right.png'
import transitionLeftUrl from '../assets/characters/crimson-elf/sprites/transition-idle-to-walk-left.png'
import transitionRightUrl from '../assets/characters/crimson-elf/sprites/transition-idle-to-walk-right.png'
import transitionFrontLeftUrl from '../assets/characters/crimson-elf/sprites/transition-idle-to-walk-front-left.png'
import transitionFrontRightUrl from '../assets/characters/crimson-elf/sprites/transition-idle-to-walk-front-right.png'
import type { ActionDefinition, PetAction, SpriteSheetSource, TransitionAction, WalkAction } from '../types/pet'

export type CrimsonElfCoreAction =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'displeased'
  | 'shy'
  | 'open-app'

export const crimsonElfSpriteSheetKeys = {
  idle: 'idle',
  listening: 'listening',
  thinking: 'thinking',
  speaking: 'speaking',
  displeased: 'displeased',
  shy: 'shy',
  'open-app': 'open-app',
} satisfies Record<CrimsonElfCoreAction, string>

const standardFrameIndices = Array.from({ length: 32 }, (_, index) => index)
// 一轮 32 帧中，首尾各 3 帧是直立启停/停顿姿态；窗口只在第 3–28 帧移动。
const walkMovementFrameIndices = Array.from({ length: 26 }, (_, index) => index + 3)
const standardBlankFrames = [32, 33, 34, 35]
const transitionFrameIndices = Array.from({ length: 16 }, (_, index) => index)

function createStandardSheet(fileName: string, src: string): SpriteSheetSource {
  return {
    src,
    fileName,
    width: 3840,
    height: 3840,
    frameWidth: 640,
    frameHeight: 640,
    columns: 6,
    rows: 6,
    frameCount: 36,
    validFrameIndices: standardFrameIndices,
    blankFrameIndices: standardBlankFrames,
    anchor: 'bottom-center',
  }
}

function createTransitionSheet(fileName: string, src: string): SpriteSheetSource {
  return {
    src,
    fileName,
    width: 2560,
    height: 2560,
    frameWidth: 640,
    frameHeight: 640,
    columns: 4,
    rows: 4,
    frameCount: 16,
    validFrameIndices: transitionFrameIndices,
    blankFrameIndices: [],
    anchor: 'bottom-center',
  }
}

export const crimsonElfIdleSpriteSheetKey = 'idle'
export const crimsonElfIdleToFrontRightSpriteSheetKey = 'transition-idle-to-walk-front-right'
export const crimsonElfThinkingSpriteSheetKey = 'thinking'

export const crimsonElfWalkSpriteSheetKeys: Record<WalkAction, string> = {
  'walk-left': 'walk-left',
  'walk-right': 'walk-right',
  'walk-front-left': 'walk-front-left',
  'walk-front-right': 'walk-front-right',
  'walk-back-left': 'walk-back-left',
  'walk-back-right': 'walk-back-right',
}

const coreUrls = {
  idle: idleUrl,
  listening: listeningUrl,
  thinking: thinkingUrl,
  speaking: speakingUrl,
  displeased: displeasedUrl,
  shy: shyUrl,
  'open-app': openAppUrl,
} as const

const coreLabels = {
  idle: '待机',
  listening: '聆听',
  thinking: '思考',
  speaking: '说话',
  displeased: '不悦',
  shy: '害羞',
  'open-app': '打开应用',
} as const

const crimsonElfWalkUrls: Record<WalkAction, string> = {
  'walk-left': walkLeftUrl,
  'walk-right': walkRightUrl,
  'walk-front-left': walkFrontLeftUrl,
  'walk-front-right': walkFrontRightUrl,
  'walk-back-left': walkBackLeftUrl,
  'walk-back-right': walkBackRightUrl,
}

const crimsonElfWalkLabels: Record<WalkAction, string> = {
  'walk-left': '向左行走',
  'walk-right': '向右行走',
  'walk-front-left': '向前左行走',
  'walk-front-right': '向前右行走',
  'walk-back-left': '向后左行走',
  'walk-back-right': '向后右行走',
}

const transitionUrls: Record<TransitionAction, string> = {
  'transition-idle-to-walk-left': transitionLeftUrl,
  'transition-idle-to-walk-right': transitionRightUrl,
  'transition-idle-to-walk-front-left': transitionFrontLeftUrl,
  'transition-idle-to-walk-front-right': transitionFrontRightUrl,
}

const transitionLabels: Record<TransitionAction, string> = {
  'transition-idle-to-walk-left': '待机转向左行走',
  'transition-idle-to-walk-right': '待机转向右行走',
  'transition-idle-to-walk-front-left': '待机转前左行走',
  'transition-idle-to-walk-front-right': '待机转前右行走',
}

export function createCrimsonElfIdleSpriteSheet(): SpriteSheetSource {
  return createStandardSheet('idle.png', idleUrl)
}

export function createCrimsonElfIdleToFrontRightSpriteSheet(): SpriteSheetSource {
  return createTransitionSheet('transition-idle-to-walk-front-right.png', transitionFrontRightUrl)
}

export function createCrimsonElfIdleToFrontRightAction(): Record<TransitionAction, ActionDefinition> {
  return createCrimsonElfTransitionActions()
}

export function createCrimsonElfThinkingSpriteSheet(): SpriteSheetSource {
  return createStandardSheet('thinking.png', thinkingUrl)
}

export function createCrimsonElfCoreSpriteSheets(): Record<keyof typeof coreUrls, SpriteSheetSource> {
  return Object.fromEntries(
    (Object.keys(coreUrls) as Array<keyof typeof coreUrls>).map((action) => [
      action,
      createStandardSheet(`${action}.png`, coreUrls[action]),
    ]),
  ) as Record<keyof typeof coreUrls, SpriteSheetSource>
}

export function createCrimsonElfCoreActions(): Partial<Record<PetAction, ActionDefinition>> {
  return Object.fromEntries(
    (Object.keys(coreLabels) as Array<keyof typeof coreLabels>).map((action) => [
      action,
      {
        id: action,
        label: coreLabels[action],
        sheet: action,
        frameIndices: standardFrameIndices,
        fps: 8,
        loop: true,
        interruptible: true,
        anchor: 'bottom-center',
      },
    ]),
  ) as Partial<Record<PetAction, ActionDefinition>>
}

export function createCrimsonElfTransitionSpriteSheets(): Record<TransitionAction, SpriteSheetSource> {
  return Object.fromEntries(
    (Object.keys(transitionUrls) as TransitionAction[]).map((action) => {
      const fileName = `${action}.png`
      return [action, createTransitionSheet(fileName, transitionUrls[action])]
    }),
  ) as Record<TransitionAction, SpriteSheetSource>
}

export function createCrimsonElfTransitionActions(): Record<TransitionAction, ActionDefinition> {
  return Object.fromEntries(
    (Object.keys(transitionLabels) as TransitionAction[]).map((action) => [
      action,
      {
        id: action,
        label: transitionLabels[action],
        sheet: action,
        frameIndices: transitionFrameIndices,
        fps: 8,
        loop: false,
        interruptible: false,
        anchor: 'bottom-center',
      },
    ]),
  ) as Record<TransitionAction, ActionDefinition>
}

export function createCrimsonElfWalkSpriteSheets(): Record<WalkAction, SpriteSheetSource> {
  return Object.fromEntries(
    (Object.keys(crimsonElfWalkSpriteSheetKeys) as WalkAction[]).map((action) => [
      crimsonElfWalkSpriteSheetKeys[action],
      createStandardSheet(`${action}.png`, crimsonElfWalkUrls[action]),
    ]),
  ) as Record<WalkAction, SpriteSheetSource>
}

export function createCrimsonElfWalkActions(): Record<WalkAction, ActionDefinition> {
  return Object.fromEntries(
    (Object.keys(crimsonElfWalkSpriteSheetKeys) as WalkAction[]).map((action) => [
      action,
      {
        id: action,
        label: crimsonElfWalkLabels[action],
        sheet: crimsonElfWalkSpriteSheetKeys[action],
        frameIndices: standardFrameIndices,
        movementFrameIndices: walkMovementFrameIndices,
        fps: 8,
        loop: true,
        interruptible: true,
        anchor: 'bottom-center',
      },
    ]),
  ) as Record<WalkAction, ActionDefinition>
}
