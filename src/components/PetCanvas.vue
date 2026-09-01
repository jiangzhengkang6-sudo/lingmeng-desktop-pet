<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { SpriteAnimator } from '../engine/SpriteAnimator'
import type { MouthMode, PetAction, PetEvent, SpriteManifest } from '../types/pet'

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
const animator = new SpriteAnimator(props.manifest)
let animationFrame = 0
let lastTime = 0

watch(() => props.manifest, (manifest) => animator.setManifest(manifest), { deep: true })
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

function render() {
  const element = canvas.value
  if (!element) return
  const ctx = element.getContext('2d')
  if (!ctx) return
  const snapshot = animator.snapshot()
  ctx.clearRect(0, 0, element.width, element.height)
  drawPlaceholder(ctx, snapshot.action, props.mouthMode, snapshot.frameIndex)
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
