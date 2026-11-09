import type { PetAction } from '../types/pet'

export const availablePetActions = [
  'idle',
  'listening',
  'thinking',
  'speaking',
  'displeased',
  'shy',
  'open-app',
] as const satisfies readonly PetAction[]

const legacyActionAliases: Partial<Record<PetAction, PetAction>> = {
  success: 'open-app',
  working: 'open-app',
  failure: 'displeased',
  refuse: 'displeased',
  sleeping: 'idle',
  reminder: 'idle',
}

export function normalizePetAction(action: string | null | undefined): PetAction {
  if (action && (availablePetActions as readonly string[]).includes(action)) {
    return action as PetAction
  }
  if (action && action in legacyActionAliases) {
    return legacyActionAliases[action as PetAction] ?? 'idle'
  }
  return 'idle'
}

export function isAvailablePetAction(action: string): action is PetAction {
  return normalizePetAction(action) === action && (availablePetActions as readonly string[]).includes(action)
}
