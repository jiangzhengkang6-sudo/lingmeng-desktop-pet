export type PetAction =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'working'
  | 'success'
  | 'failure'
  | 'refuse'
  | 'sleeping'
  | 'reminder'

export type MouthMode = 'closed' | 'half-open' | 'open'

export type ActionDefinition = {
  id: PetAction
  label: string
  frameIndices: number[]
  fps: number
  loop: boolean
  interruptible: boolean
}

export type SpriteManifest = {
  name: string
  version: string
  canvas: {
    width: number
    height: number
    background: 'transparent'
  }
  actions: Partial<Record<PetAction, ActionDefinition>>
}

export type PetEvent = {
  action: PetAction
  emotion?: string
  mouthMode?: MouthMode
  durationMs?: number
  interruptible?: boolean
}
