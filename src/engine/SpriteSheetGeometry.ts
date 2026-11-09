export type SpriteSheetGeometry = {
  columns: number
  rows: number
  frameCount: number
}

export function calculateSpriteSheetGeometry(
  width: number,
  height: number,
  frameWidth: number,
  frameHeight: number,
): SpriteSheetGeometry {
  if (frameWidth <= 0 || frameHeight <= 0) {
    return { columns: 0, rows: 0, frameCount: 0 }
  }

  const columns = Math.floor(width / frameWidth)
  const rows = Math.floor(height / frameHeight)
  return {
    columns,
    rows,
    frameCount: columns * rows,
  }
}
