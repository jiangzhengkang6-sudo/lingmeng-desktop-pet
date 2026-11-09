<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  color?: string
  secondaryColor?: string
  trailLength?: number
  trailWidth?: number
  followSpeed?: number
  glowIntensity?: number
  brightness?: number
  opacity?: number
  idleTimeout?: number
  fadeDuration?: number
  maxDevicePixelRatio?: number
  enabled?: boolean
}>(), {
  color: '#22d3ee',
  secondaryColor: '#f472b6',
  trailLength: 42,
  trailWidth: 8,
  followSpeed: .18,
  glowIntensity: 1.7,
  brightness: 1.25,
  opacity: .95,
  idleTimeout: 650,
  fadeDuration: 800,
  maxDevicePixelRatio: 1.5,
  enabled: true,
})

const canvas = ref<HTMLCanvasElement | null>(null)
let context: CanvasRenderingContext2D | null = null
let raf = 0
let destroyed = false
let dpr = 1
let pointerX = window.innerWidth / 2
let pointerY = window.innerHeight / 2
let initialized = false
let pointerInside = true
let lastInput = performance.now()
let fade = 0
let lastFrame = performance.now()

type Point = { x: number; y: number }
const MAX_POINTS = 64
const points: Point[] = Array.from({ length: MAX_POINTS }, () => ({ x: pointerX, y: pointerY }))

function resize() {
  const element = canvas.value
  if (!element) return
  dpr = Math.min(window.devicePixelRatio || 1, props.maxDevicePixelRatio)
  element.width = Math.floor(window.innerWidth * dpr)
  element.height = Math.floor(window.innerHeight * dpr)
  element.style.width = `${window.innerWidth}px`
  element.style.height = `${window.innerHeight}px`
  context = element.getContext('2d')
  context?.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function updatePointer(event: PointerEvent) {
  pointerX = event.clientX
  pointerY = event.clientY
  pointerInside = true
  initialized = true
  lastInput = performance.now()
}

function onPointerLeave() {
  pointerInside = false
  lastInput = performance.now()
}

function hexToRgb(hex: string) {
  const normalized = hex.trim().replace('#', '')
  const full = normalized.length === 3
    ? normalized.split('').map((char) => char + char).join('')
    : normalized
  const value = Number.parseInt(full, 16)
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  }
}

function drawSegment(start: Point, end: Point, index: number, count: number) {
  if (!context) return
  const progress = index / Math.max(count - 1, 1)
  const head = hexToRgb(props.color)
  const tail = hexToRgb(props.secondaryColor)
  const r = Math.round(head.r + (tail.r - head.r) * progress)
  const g = Math.round(head.g + (tail.g - head.g) * progress)
  const b = Math.round(head.b + (tail.b - head.b) * progress)
  const alpha = (1 - progress) * fade * props.opacity
  const width = Math.max(.8, props.trailWidth * (1 - progress * .78))

  context.globalCompositeOperation = 'screen'
  context.strokeStyle = `rgba(${r},${g},${b},${alpha * .32 * props.glowIntensity})`
  context.lineWidth = width * 4.2
  context.beginPath()
  context.moveTo(start.x, start.y)
  context.lineTo(end.x, end.y)
  context.stroke()

  context.strokeStyle = `rgba(${r},${g},${b},${alpha})`
  context.lineWidth = width
  context.beginPath()
  context.moveTo(start.x, start.y)
  context.lineTo(end.x, end.y)
  context.stroke()
}

function drawHead() {
  if (!context || !initialized) return
  const head = points[0]
  const radius = props.trailWidth * 2.4
  const gradient = context.createRadialGradient(head.x, head.y, 0, head.x, head.y, radius)
  const color = hexToRgb(props.color)
  gradient.addColorStop(0, `rgba(255,255,255,${.85 * fade * props.brightness})`)
  gradient.addColorStop(.22, `rgba(${color.r},${color.g},${color.b},${.55 * fade})`)
  gradient.addColorStop(1, 'rgba(0,0,0,0)')
  context.globalCompositeOperation = 'screen'
  context.fillStyle = gradient
  context.beginPath()
  context.arc(head.x, head.y, radius, 0, Math.PI * 2)
  context.fill()
}

function render(now: number) {
  if (destroyed) return
  const delta = Math.min((now - lastFrame) / 16.667, 3)
  lastFrame = now
  if (context) {
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.globalCompositeOperation = 'source-over'
    context.clearRect(0, 0, window.innerWidth, window.innerHeight)
    context.lineCap = 'round'
    context.lineJoin = 'round'
  }

  if (initialized) {
    const headEase = 1 - (1 - Math.min(Math.max(props.followSpeed, .02), .98)) ** delta
    points[0].x += (pointerX - points[0].x) * headEase
    points[0].y += (pointerY - points[0].y) * headEase
    const chainBase = Math.min(Math.max(.18 + props.followSpeed * .32, .08), .9)
    const chainEase = 1 - (1 - chainBase) ** delta
    for (let index = 1; index < MAX_POINTS; index += 1) {
      points[index].x += (points[index - 1].x - points[index].x) * chainEase
      points[index].y += (points[index - 1].y - points[index].y) * chainEase
    }
  }

  const idleFor = now - lastInput
  const shouldFade = !props.enabled || !pointerInside || idleFor > props.idleTimeout
  const targetFade = shouldFade ? 0 : 1
  const fadeStep = (16.667 * delta) / Math.max(props.fadeDuration, 16)
  fade += (targetFade - fade) * Math.min(1, fadeStep * 7)

  const count = Math.min(Math.max(Math.round(props.trailLength), 2), MAX_POINTS)
  for (let index = count - 2; index >= 0; index -= 1) {
    drawSegment(points[index], points[index + 1], index, count)
  }
  drawHead()
  raf = requestAnimationFrame(render)
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', updatePointer)
  document.documentElement.addEventListener('pointerleave', onPointerLeave)
  lastFrame = performance.now()
  raf = requestAnimationFrame(render)
})

onBeforeUnmount(() => {
  destroyed = true
  cancelAnimationFrame(raf)
  window.removeEventListener('resize', resize)
  window.removeEventListener('pointermove', updatePointer)
  document.documentElement.removeEventListener('pointerleave', onPointerLeave)
})
</script>

<template>
  <canvas ref="canvas" class="glow-cursor" aria-hidden="true" />
</template>

<style scoped>
.glow-cursor {
  position: fixed;
  inset: 0;
  z-index: 90;
  pointer-events: none;
  mix-blend-mode: screen;
}

@media (prefers-reduced-motion: reduce) {
  .glow-cursor { display: none; }
}
</style>
