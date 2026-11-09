<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolveSpriteSheet } from '../engine/ResourcePackage'
import { SpriteAnimator } from '../engine/SpriteAnimator'
import type { MouthMode, PetAction, PetEvent, SpriteManifest, SpriteSheetSource } from '../types/pet'

const props = defineProps<{
  action: PetAction
  mouthMode: MouthMode
  manifest: SpriteManifest
  paused: boolean
}>()

const emit = defineEmits<{
  snapshot: [snapshot: ReturnType<SpriteAnimator['snapshot']>]
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const spriteImages = ref<Record<string, HTMLImageElement | null>>({})
const animator = new SpriteAnimator(props.manifest)
let animationFrame = 0
let lastTime = 0

const currentSourceKey = computed(() => {
  const actionDefinition = props.manifest.actions[props.action]
  const source = resolveSpriteSheet(props.manifest, actionDefinition)
  return source ? findSourceKey(source) : undefined
})

watch(() => props.manifest, (manifest) => animator.setManifest(manifest), { deep: true })
watch([
  () => props.manifest,
  () => currentSourceKey.value,
], () => loadCurrentSpriteSheet(), { deep: true, immediate: true })
watch(() => props.manifest.spriteSheets, () => preloadManifestSheets(), { deep: true, immediate: true })
watch(() => props.manifest.spriteSheet?.src, () => preloadManifestSheets(), { immediate: true })
watch(() => props.action, (action) => {
  const event: PetEvent = { action, mouthMode: props.mouthMode }
  animator.dispatch(event)
})
watch(() => props.paused, (paused) => paused ? animator.pause() : animator.resume())

function drawPlaceholder(ctx: CanvasRenderingContext2D, action: PetAction, mouthMode: MouthMode, frame: number) {
  const { width, height } = ctx.canvas
  const cx = width / 2
  const ground = height * 0.82
  const bob = action === 'idle' ? Math.sin(frame * 0.08) * 4 : 0
  const tilt = action === 'thinking' ? -0.06 : action === 'success' ? 0.04 : 0
  const skin = '#f6d5c5'
  const wine = '#6d1f32'
  const ink = '#271821'
  const gold = '#d7a35e'

  ctx.save()
  ctx.translate(cx, ground - bob)
  ctx.rotate(tilt)
  ctx.fillStyle = 'rgba(36, 18, 30, .18)'
  ctx.beginPath()
  ctx.ellipse(0, 16, 102, 16, 0, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = wine
  ctx.beginPath()
  ctx.moveTo(-72, -210)
  ctx.lineTo(-105, 4)
  ctx.quadraticCurveTo(0, 42, 105, 4)
  ctx.lineTo(72, -210)
  ctx.closePath()
  ctx.fill()
  ctx.strokeStyle = gold
  ctx.lineWidth = 3
  ctx.stroke()

  ctx.fillStyle = skin
  ctx.beginPath()
  ctx.arc(0, -267, 61, 0, Math.PI * 2)
  ctx.fill()
  ctx.strokeStyle = ink
  ctx.lineWidth = 5
  ctx.stroke()

  ctx.fillStyle = '#e9bd80'
  ctx.beginPath()
  ctx.moveTo(-69, -282)
  ctx.quadraticCurveTo(-84, -388, -20, -332)
  ctx.quadraticCurveTo(0, -368, 20, -332)
  ctx.quadraticCurveTo(84, -388, 69, -282)
  ctx.quadraticCurveTo(45, -337, 0, -331)
  ctx.quadraticCurveTo(-45, -337, -69, -282)
  ctx.fill()
  ctx.strokeStyle = ink
  ctx.stroke()

  ctx.fillStyle = '#9c3044'
  ctx.beginPath()
  ctx.arc(-58, -326, 15, 0, Math.PI * 2)
  ctx.arc(58, -326, 15, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = ink
  ctx.beginPath()
  ctx.ellipse(-22, -267, 7, action === 'sleeping' ? 3 : 12, 0, 0, Math.PI * 2)
  ctx.ellipse(22, -267, 7, action === 'sleeping' ? 3 : 12, 0, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = '#9c3044'
  ctx.lineWidth = mouthMode === 'open' ? 8 : mouthMode === 'half-open' ? 4 : 3
  ctx.beginPath()
  if (mouthMode === 'open') ctx.arc(0, -238, 12, 0, Math.PI)
  else ctx.arc(0, -242, 10, 0.15, Math.PI - 0.15)
  ctx.stroke()
  ctx.restore()
}

function sourceEntries() {
  const entries = Object.entries(props.manifest.spriteSheets ?? {})
  if (entries.length > 0) return entries
  return props.manifest.spriteSheet ? [['default', props.manifest.spriteSheet] as const] : []
}

function hasSpriteManifest() {
  return sourceEntries().length > 0
}

function beginImageLoad(key: string, src: string) {
  if (spriteImages.value[key]) return
  const image = new Image()
  image.onload = () => {
    spriteImages.value = { ...spriteImages.value, [key]: image }
  }
  image.onerror = () => {
    spriteImages.value = { ...spriteImages.value, [key]: null }
  }
  image.src = src
}

function preloadManifestSheets() {
  for (const [key, source] of sourceEntries()) {
    if (source.src && !spriteImages.value[key]) beginImageLoad(key, source.src)
  }
}

function loadCurrentSpriteSheet() {
  const entries = sourceEntries()
  const key = currentSourceKey.value
  if (!key) return
  if (spriteImages.value[key]) return
  const source = entries.find(([candidate]) => candidate === key)?.[1]
  if (!source?.src) {
    spriteImages.value = { ...spriteImages.value, [key]: null }
    return
  }
  beginImageLoad(key, source.src)
}

function findSourceKey(source: SpriteSheetSource) {
  const byIdentity = sourceEntries().find(([, candidate]) => candidate === source)
  if (byIdentity) return byIdentity[0]
  return sourceEntries().find(([, candidate]) => candidate.fileName === source.fileName)?.[0]
}


const lastRendered = {
  key: '' as string,
  image: null as HTMLImageElement | null,
  source: null as SpriteSheetSource | null,
  actionDefinition: null as SpriteManifest['actions'][PetAction] | null,
}

function drawSpriteFrame(ctx: CanvasRenderingContext2D, action: PetAction, frameIndex: number) {
  const actionDefinition = props.manifest.actions[action]
  const source = resolveSpriteSheet(props.manifest, actionDefinition)
  const sourceKey = source ? findSourceKey(source) : undefined
  const image = sourceKey ? spriteImages.value[sourceKey] : null
  if (!source || source.frameWidth <= 0 || source.frameHeight <= 0 || source.columns <= 0) {
    lastRendered.key = ''
    lastRendered.image = null
    lastRendered.source = null
    lastRendered.actionDefinition = null
    return false
  }
  if (!image || !image.complete || image.naturalWidth === 0) {
    // 当前动作的图片尚未加载完成时，若上一张成功渲染的图存在则继续显示它
    // （保持动作切换时画面不闪烁，用的是上次成功时对应的 source/action）。
    if (lastRendered.image && lastRendered.key && lastRendered.source && lastRendered.actionDefinition) {
      return drawLoadedSpriteFrame(
        ctx,
        lastRendered.image,
        lastRendered.source,
        lastRendered.actionDefinition,
        lastRendered.key,
        frameIndex,
        true,
      )
    }
    return false
  }

  return drawLoadedSpriteFrame(ctx, image, source, actionDefinition, sourceKey ?? '', frameIndex, false)
}

function drawLoadedSpriteFrame(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  source: SpriteSheetSource,
  actionDefinition: SpriteManifest['actions'][PetAction],
  sourceKey: string,
  frameIndex: number,
  previousFrame: boolean,
) {
  const frame = previousFrame ? 0 : frameIndex
  const column = frame % source.columns
  const row = Math.floor(frame / source.columns)
  const sx = column * source.frameWidth
  const sy = row * source.frameHeight
  if (sx + source.frameWidth > image.naturalWidth || sy + source.frameHeight > image.naturalHeight) return false

  const scale = Math.min(460 / source.frameWidth, 460 / source.frameHeight)
  const width = source.frameWidth * scale
  const height = source.frameHeight * scale
  const anchor = actionDefinition?.anchor ?? source.anchor
  const dx = (ctx.canvas.width - width) / 2
  const dy = anchor === 'bottom-center'
    ? ctx.canvas.height * 0.82 - height
    : (ctx.canvas.height - height) / 2
  ctx.drawImage(image, sx, sy, source.frameWidth, source.frameHeight, dx, dy, width, height)
  if (!previousFrame) {
    lastRendered.key = sourceKey
    lastRendered.image = image
    lastRendered.source = source
    lastRendered.actionDefinition = actionDefinition
  }
  return true
}

function render() {
  const element = canvas.value
  if (!element) return
  const ctx = element.getContext('2d')
  if (!ctx) return
  const snapshot = animator.snapshot()
  ctx.clearRect(0, 0, element.width, element.height)
  if (!drawSpriteFrame(ctx, snapshot.action, snapshot.frameIndex)) {
    if (!hasSpriteManifest()) drawPlaceholder(ctx, snapshot.action, props.mouthMode, snapshot.frameIndex)
  }
  emit('snapshot', snapshot)
}

function loop(time: number) {
  const delta = lastTime ? Math.min(100, time - lastTime) : 16
  lastTime = time
  animator.tick(delta)
  render()
  animationFrame = requestAnimationFrame(loop)
}

onMounted(() => {
  animator.dispatch({ action: props.action, mouthMode: props.mouthMode })
  animationFrame = requestAnimationFrame(loop)
})

onBeforeUnmount(() => cancelAnimationFrame(animationFrame))
</script>

<template>
  <canvas ref="canvas" class="pet-canvas" width="520" height="520" aria-label="Canvas 桌宠预览" />
</template>
