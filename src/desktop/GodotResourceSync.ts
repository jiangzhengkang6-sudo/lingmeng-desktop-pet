import { invoke, isTauri } from '@tauri-apps/api/core'
import { toManifestJson } from '../engine/ResourcePackage'
import type { ManifestJson } from '../engine/ResourcePackage'
import type { SpriteManifest, SpriteSheetSource } from '../types/pet'

export type GodotResourceImage = {
  sheetKey: string
  dataUrl: string
}

export type GodotResourcePackagePayload = {
  manifest: ManifestJson
  images: GodotResourceImage[]
}

export type GodotResourceSyncResult = {
  manifestPath: string
  imageCount: number
}

function registeredSources(manifest: SpriteManifest) {
  return manifest.spriteSheets ?? (manifest.spriteSheet ? { default: manifest.spriteSheet } : {})
}

function isPngDataUrl(value: string) {
  return value.startsWith('data:image/png;base64,')
}

function blobToDataUrl(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => typeof reader.result === 'string'
      ? resolve(reader.result)
      : reject(new Error('无法读取 SpriteSheet 图片'))
    reader.onerror = () => reject(new Error('无法读取 SpriteSheet 图片'))
    reader.readAsDataURL(blob)
  })
}

async function sourceToPngDataUrl(source: SpriteSheetSource) {
  if (isPngDataUrl(source.src)) return source.src

  const response = await fetch(source.src)
  if (!response.ok) throw new Error(`${source.fileName} 无法读取为 PNG`)
  const blob = await response.blob()
  if (blob.type && blob.type !== 'image/png') {
    throw new Error(`${source.fileName} 不是 PNG 图片`)
  }
  return blobToDataUrl(blob)
}

export async function createGodotResourcePackagePayload(manifest: SpriteManifest): Promise<GodotResourcePackagePayload> {
  const sources = registeredSources(manifest)
  const entries = Object.entries(sources)
  if (entries.length === 0) throw new Error('请先导入至少一张 PNG SpriteSheet')

  const packageManifest = toManifestJson(manifest)
  const spriteSheets = packageManifest.sprite_sheets
  if (!spriteSheets) throw new Error('资源包缺少 SpriteSheet 清单')

  const images = await Promise.all(entries.map(async ([sheetKey, source]) => ({
    sheetKey,
    dataUrl: await sourceToPngDataUrl(source),
  })))

  return {
    manifest: packageManifest,
    images,
  }
}

export async function syncResourcePackageToGodot(manifest: SpriteManifest): Promise<GodotResourceSyncResult> {
  if (!isTauri()) throw new Error('Godot 同步仅支持 Tauri 桌面版')

  return invoke<GodotResourceSyncResult>('sync_godot_resource_package', {
    package: await createGodotResourcePackagePayload(manifest),
  })
}
