import { cloneManifestForTransport } from './ResourcePackage'
import type { SpriteManifest } from '../types/pet'

const DATABASE_NAME = 'canvas-pet-resource-package'
const DATABASE_VERSION = 1
const STORE_NAME = 'packages'
const PACKAGE_KEY = 'current'

export type StoredResourcePackage = {
  schemaVersion: 1
  savedAt: string
  manifest: SpriteManifest
}

export function createStoredResourcePackage(
  manifest: SpriteManifest,
  savedAt = new Date().toISOString(),
): StoredResourcePackage {
  return {
    schemaVersion: 1,
    savedAt,
    manifest: cloneManifestForTransport(manifest),
  }
}

function openDatabase(): Promise<IDBDatabase> {
  if (!globalThis.indexedDB) {
    return Promise.reject(new Error('当前环境不支持本地资源保存'))
  }

  return new Promise((resolve, reject) => {
    const request = globalThis.indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error('无法打开本地资源存储'))
  })
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error('本地资源存储操作失败'))
  })
}

export async function saveResourcePackage(manifest: SpriteManifest): Promise<void> {
  const database = await openDatabase()
  try {
    const store = database.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME)
    await requestResult(store.put(createStoredResourcePackage(manifest), PACKAGE_KEY))
  } finally {
    database.close()
  }
}

export async function loadResourcePackage(): Promise<StoredResourcePackage | null> {
  const database = await openDatabase()
  try {
    const store = database.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME)
    const value = await requestResult(store.get(PACKAGE_KEY))
    if (!value || typeof value !== 'object') return null
    const snapshot = value as Partial<StoredResourcePackage>
    if (snapshot.schemaVersion !== 1 || typeof snapshot.savedAt !== 'string' || !snapshot.manifest) return null
    return {
      schemaVersion: 1,
      savedAt: snapshot.savedAt,
      manifest: cloneManifestForTransport(snapshot.manifest),
    }
  } finally {
    database.close()
  }
}

export async function clearResourcePackage(): Promise<void> {
  const database = await openDatabase()
  try {
    const store = database.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME)
    await requestResult(store.delete(PACKAGE_KEY))
  } finally {
    database.close()
  }
}
