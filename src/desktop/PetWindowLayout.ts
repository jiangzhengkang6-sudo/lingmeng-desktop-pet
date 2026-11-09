export const PET_WINDOW_MIN_SIZE = 120
export const PET_WINDOW_MAX_SIZE = 480
export const PET_WINDOW_DEFAULT_SCREEN_RATIO = 0.26
export const PET_WINDOW_SNAP_DISTANCE = 20

export type PhysicalPoint = {
  x: number
  y: number
}

export type PhysicalArea = PhysicalPoint & {
  width: number
  height: number
}

export function clampPetWindowSize(size: number) {
  return Math.min(PET_WINDOW_MAX_SIZE, Math.max(PET_WINDOW_MIN_SIZE, Math.round(size)))
}

export function defaultPetWindowSize(workAreaWidth: number, workAreaHeight: number) {
  return clampPetWindowSize(Math.min(workAreaWidth, workAreaHeight) * PET_WINDOW_DEFAULT_SCREEN_RATIO)
}

export function snapPetWindowPosition(
  position: PhysicalPoint,
  size: Pick<PhysicalArea, 'width' | 'height'>,
  workArea: PhysicalArea,
  snapDistance = PET_WINDOW_SNAP_DISTANCE,
) {
  const right = workArea.x + workArea.width - size.width
  const bottom = workArea.y + workArea.height - size.height
  const x = Math.abs(position.x - workArea.x) <= snapDistance
    ? workArea.x
    : Math.abs(position.x - right) <= snapDistance
      ? right
      : position.x
  const y = Math.abs(position.y - workArea.y) <= snapDistance
    ? workArea.y
    : Math.abs(position.y - bottom) <= snapDistance
      ? bottom
      : position.y

  return { x, y }
}
