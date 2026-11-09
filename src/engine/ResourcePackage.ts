import type { ActionDefinition, PetResourceAction, SpriteAnchor, SpriteManifest, SpriteSheetSource } from '../types/pet'

const actionIds: PetResourceAction[] = [
  'idle', 'listening', 'thinking', 'speaking',
  'displeased', 'shy', 'open-app', 'working',
  'success', 'failure', 'refuse', 'sleeping', 'reminder',
  'walk-left', 'walk-right', 'walk-front-left',
  'walk-front-right', 'walk-back-left', 'walk-back-right',
  'transition-idle-to-walk-left',
  'transition-idle-to-walk-right',
  'transition-idle-to-walk-front-left',
  'transition-idle-to-walk-front-right',
]

const anchors: SpriteAnchor[] = ['bottom-center', 'center']

export type SpriteSheetJson = {
  file?: string
  width: number
  height: number
  frame_width: number
  frame_height: number
  columns: number
  rows: number
  frame_count: number
  valid_frame_indices?: number[]
  blank_frame_indices?: number[]
  anchor?: string
}

export type ActionJson = {
  schema_version?: string
  id: string
  label: string
  sheet?: string
  frame_width?: number
  frame_height?: number
  columns?: number
  rows?: number
  frame_count?: number
  valid_frame_indices?: number[]
  blank_frame_indices?: number[]
  frame_indices: number[]
  movement_frame_indices?: number[]
  fps: number
  loop: boolean
  interruptible: boolean
  anchor?: string
}

export type ManifestJson = {
  schema_version?: string
  name: string
  version: string
  canvas: {
    width: number
    height: number
    background?: string
  }
  sprite_sheets?: Record<string, SpriteSheetJson>
  // Legacy v1 field. New exports use sprite_sheets.
  sprite_sheet?: SpriteSheetJson
  actions: Record<string, ActionJson>
}

export type ResourcePackageImport = {
  manifest?: SpriteManifest
  action?: ActionDefinition
  spriteSheets?: Record<string, Partial<SpriteSheetSource>>
  spriteSheet?: Partial<SpriteSheetSource>
}

function asFiniteNumber(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asIntegerArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is number => Number.isInteger(item)) : []
}

function asAnchor(value: unknown): SpriteAnchor {
  return typeof value === 'string' && anchors.includes(value as SpriteAnchor) ? value as SpriteAnchor : 'bottom-center'
}

function asActionId(value: unknown): PetResourceAction | null {
  return typeof value === 'string' && actionIds.includes(value as PetResourceAction) ? value as PetResourceAction : null
}

function parseSpriteSheet(rawSource: Partial<SpriteSheetJson>): Partial<SpriteSheetSource> {
  return {
    fileName: typeof rawSource.file === 'string' ? rawSource.file : '',
    width: asFiniteNumber(rawSource.width),
    height: asFiniteNumber(rawSource.height),
    frameWidth: asFiniteNumber(rawSource.frame_width),
    frameHeight: asFiniteNumber(rawSource.frame_height),
    columns: asFiniteNumber(rawSource.columns),
    rows: asFiniteNumber(rawSource.rows),
    frameCount: asFiniteNumber(rawSource.frame_count),
    validFrameIndices: asIntegerArray(rawSource.valid_frame_indices),
    blankFrameIndices: asIntegerArray(rawSource.blank_frame_indices),
    anchor: asAnchor(rawSource.anchor),
  }
}

function sourceKey(source: Partial<SpriteSheetSource>, fallback = 'default') {
  return source.fileName || fallback
}

export function resolveSpriteSheet(manifest: SpriteManifest, action?: ActionDefinition): SpriteSheetSource | undefined {
  const sources = manifest.spriteSheets
  const requested = action?.sheet
  if (sources) {
    if (requested && sources[requested]) return sources[requested]
    if (requested) {
      return Object.values(sources).find((source) => source.fileName === requested)
    }
    if (manifest.spriteSheet) return manifest.spriteSheet
    return Object.values(sources)[0]
  }
  return manifest.spriteSheet
}

export function toActionJson(action: ActionDefinition, source?: SpriteSheetSource): ActionJson {
  return {
    schema_version: '1.0',
    id: action.id,
    label: action.label,
    sheet: action.sheet ?? source?.fileName,
    frame_width: source?.frameWidth,
    frame_height: source?.frameHeight,
    columns: source?.columns,
    rows: source?.rows,
    frame_count: source?.frameCount,
    valid_frame_indices: source?.validFrameIndices,
    blank_frame_indices: source?.blankFrameIndices,
    frame_indices: action.frameIndices,
    movement_frame_indices: action.movementFrameIndices,
    fps: action.fps,
    loop: action.loop,
    interruptible: action.interruptible,
    anchor: action.anchor,
  }
}

function toSpriteSheetJson(source: SpriteSheetSource): SpriteSheetJson {
  return {
    file: source.fileName,
    width: source.width,
    height: source.height,
    frame_width: source.frameWidth,
    frame_height: source.frameHeight,
    columns: source.columns,
    rows: source.rows,
    frame_count: source.frameCount,
    valid_frame_indices: source.validFrameIndices,
    blank_frame_indices: source.blankFrameIndices,
    anchor: source.anchor,
  }
}

export function toManifestJson(manifest: SpriteManifest): ManifestJson {
  const sources = manifest.spriteSheets ?? (manifest.spriteSheet ? { [sourceKey(manifest.spriteSheet)]: manifest.spriteSheet } : {})
  return {
    schema_version: manifest.schemaVersion,
    name: manifest.name,
    version: manifest.version,
    canvas: { ...manifest.canvas },
    sprite_sheets: Object.fromEntries(Object.entries(sources).map(([key, source]) => [key, toSpriteSheetJson(source)])),
    actions: Object.fromEntries(
      Object.entries(manifest.actions)
        .filter((entry): entry is [string, ActionDefinition] => Boolean(entry[1]))
        .map(([id, action]) => [id, toActionJson(action, resolveSpriteSheet(manifest, action))]),
    ),
  }
}

export function parseManifestJson(value: unknown): ResourcePackageImport {
  if (!value || typeof value !== 'object') throw new Error('manifest.json 必须是 JSON 对象')
  const data = value as Partial<ManifestJson>
  if (
    typeof data.name !== 'string'
    || typeof data.version !== 'string'
    || !data.canvas
    || typeof data.canvas !== 'object'
    || !data.actions
    || typeof data.actions !== 'object'
    || Array.isArray(data.actions)
  ) {
    throw new Error('manifest.json 缺少 name、version、canvas 或 actions')
  }

  const rawSources = data.sprite_sheets ?? (data.sprite_sheet ? { default: data.sprite_sheet } : undefined)
  const spriteSheets = rawSources
    ? Object.fromEntries(Object.entries(rawSources).map(([key, rawSource]) => [key, parseSpriteSheet(rawSource)]))
    : undefined
  const legacySpriteSheet = data.sprite_sheet ? parseSpriteSheet(data.sprite_sheet) : spriteSheets ? Object.values(spriteSheets)[0] : undefined
  const actions: Partial<Record<PetResourceAction, ActionDefinition>> = {}
  for (const [key, rawAction] of Object.entries(data.actions)) {
    const id = asActionId(rawAction?.id ?? key)
    if (!id || !rawAction || typeof rawAction.label !== 'string') continue
    actions[id] = parseAction(rawAction, id, spriteSheets, legacySpriteSheet)
  }

  return {
    manifest: {
      schemaVersion: typeof data.schema_version === 'string' ? data.schema_version : '1.0',
      name: data.name,
      version: data.version,
      canvas: {
        width: asFiniteNumber(data.canvas.width),
        height: asFiniteNumber(data.canvas.height),
        background: 'transparent',
      },
      spriteSheets: spriteSheets as Record<string, SpriteSheetSource> | undefined,
      spriteSheet: legacySpriteSheet as SpriteSheetSource | undefined,
      actions,
    },
    spriteSheets,
    spriteSheet: legacySpriteSheet,
  }
}

export function parseActionJson(value: unknown): ResourcePackageImport {
  if (!value || typeof value !== 'object') throw new Error('action.json 必须是 JSON 对象')
  const data = value as Partial<ActionJson>
  const id = asActionId(data.id)
  if (!id || typeof data.label !== 'string' || !Array.isArray(data.frame_indices)) {
    throw new Error('action.json 缺少有效的 id、label 或 frame_indices')
  }
  const spriteSheet = data.frame_width && data.frame_height ? parseSpriteSheet({
    file: typeof data.sheet === 'string' ? data.sheet : undefined,
    width: asFiniteNumber(data.columns) * asFiniteNumber(data.frame_width),
    height: asFiniteNumber(data.rows) * asFiniteNumber(data.frame_height),
    frame_width: data.frame_width,
    frame_height: data.frame_height,
    columns: data.columns,
    rows: data.rows,
    frame_count: data.frame_count ?? asFiniteNumber(data.columns) * asFiniteNumber(data.rows),
    valid_frame_indices: data.valid_frame_indices,
    blank_frame_indices: data.blank_frame_indices,
    anchor: data.anchor,
  }) : undefined
  const action = parseAction(data, id, spriteSheet ? { [sourceKey(spriteSheet)]: spriteSheet } : undefined, spriteSheet)
  return {
    action,
    spriteSheets: spriteSheet ? { [sourceKey(spriteSheet)]: spriteSheet } : undefined,
    spriteSheet,
  }
}

function parseAction(
  raw: Partial<ActionJson>,
  id: PetResourceAction,
  sources?: Record<string, Partial<SpriteSheetSource>>,
  fallbackSource?: Partial<SpriteSheetSource>,
): ActionDefinition {
  const requestedSheet = typeof raw.sheet === 'string' ? raw.sheet : undefined
  const source = requestedSheet && sources
    ? sources[requestedSheet] ?? Object.values(sources).find((candidate) => candidate.fileName === requestedSheet)
    : fallbackSource
  const movementFrameIndices = asIntegerArray(raw.movement_frame_indices)
  return {
    id,
    label: raw.label ?? id,
    sheet: requestedSheet ?? source?.fileName,
    frameIndices: asIntegerArray(raw.frame_indices),
    ...(movementFrameIndices.length ? { movementFrameIndices } : {}),
    fps: asFiniteNumber(raw.fps),
    loop: raw.loop === true,
    interruptible: raw.interruptible !== false,
    anchor: asAnchor(raw.anchor ?? source?.anchor),
  }
}

export function downloadJson(fileName: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}

export function cloneManifestForTransport(manifest: SpriteManifest): SpriteManifest {
  return JSON.parse(JSON.stringify(manifest)) as SpriteManifest
}
