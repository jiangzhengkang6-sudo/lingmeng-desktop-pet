export type PetAction =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'displeased'
  | 'shy'
  | 'open-app'
  | 'working'
  | 'success'
  | 'failure'
  | 'refuse'
  | 'sleeping'
  | 'reminder'

export type WalkAction =
  | 'walk-left'
  | 'walk-right'
  | 'walk-front-left'
  | 'walk-front-right'
  | 'walk-back-left'
  | 'walk-back-right'

export type TransitionAction =
  | 'transition-idle-to-walk-left'
  | 'transition-idle-to-walk-right'
  | 'transition-idle-to-walk-front-left'
  | 'transition-idle-to-walk-front-right'

export type PetResourceAction = PetAction | WalkAction | TransitionAction

export function isPetAction(value: string): value is PetAction {
  return [
    'idle', 'listening', 'thinking', 'speaking',
    'displeased', 'shy', 'open-app', 'working',
    'success', 'failure', 'refuse', 'sleeping', 'reminder',
  ].includes(value as PetAction)
}

export function isWalkAction(value: string): value is WalkAction {
  return [
    'walk-left', 'walk-right', 'walk-front-left',
    'walk-front-right', 'walk-back-left', 'walk-back-right',
  ].includes(value as WalkAction)
}

export type MouthMode = 'closed' | 'half-open' | 'open'
export type SpriteAnchor = 'bottom-center' | 'center'

export type ActionDefinition = {
  id: PetResourceAction
  label: string
  sheet?: string
  frameIndices: number[]
  // 只有这些帧允许 Godot 移动桌面窗口；未配置时由 Godot 端按动作类型使用兼容默认值。
  movementFrameIndices?: number[]
  fps: number
  loop: boolean
  interruptible: boolean
  anchor: SpriteAnchor
}

export type SpriteSheetSource = {
  src: string
  fileName: string
  width: number
  height: number
  frameWidth: number
  frameHeight: number
  columns: number
  rows: number
  frameCount: number
  validFrameIndices: number[]
  blankFrameIndices: number[]
  anchor: SpriteAnchor
}

export type SpriteManifest = {
  schemaVersion: string
  name: string
  version: string
  canvas: {
    width: number
    height: number
    background: 'transparent'
  }
  spriteSheets?: Record<string, SpriteSheetSource>
  // Legacy single-sheet field kept for consumers of the v1 manifest shape.
  spriteSheet?: SpriteSheetSource
  actions: Partial<Record<PetResourceAction, ActionDefinition>>
}

export type PetEvent = {
  action: PetAction
  emotion?: string
  mouthMode?: MouthMode
  durationMs?: number
  interruptible?: boolean
}
