<script setup lang="ts">
import { computed, ref } from 'vue'
import PetCanvas from './components/PetCanvas.vue'
import type { PetAction, SpriteManifest } from './types/pet'

const actions: Array<{ id: PetAction; label: string; tone: string }> = [
  { id: 'idle', label: '待机', tone: 'calm' },
  { id: 'listening', label: '聆听', tone: 'blue' },
  { id: 'thinking', label: '思考', tone: 'violet' },
  { id: 'speaking', label: '说话', tone: 'rose' },
  { id: 'working', label: '工作中', tone: 'amber' },
  { id: 'success', label: '成功', tone: 'green' },
  { id: 'failure', label: '失败', tone: 'red' },
  { id: 'refuse', label: '拒绝', tone: 'slate' },
  { id: 'sleeping', label: '休眠', tone: 'indigo' },
  { id: 'reminder', label: '提醒', tone: 'orange' },
]

const currentAction = ref<PetAction>('idle')
const mouthMode = ref<'closed' | 'half-open' | 'open'>('closed')
const paused = ref(false)
const fps = ref(8)
const currentFrame = ref(0)
const fallback = ref(false)

const manifest = computed<SpriteManifest>(() => ({
  name: 'canvas-pet-placeholder',
  version: '0.1.0',
  canvas: { width: 520, height: 520, background: 'transparent' },
  actions: Object.fromEntries(actions.map(({ id, label }) => [
    id,
    {
      id,
      label,
      frameIndices: [0, 1, 2, 3],
      fps: fps.value,
      loop: id !== 'success' && id !== 'failure' && id !== 'refuse',
      interruptible: id !== 'working',
    },
  ])),
}))

const currentLabel = computed(() => actions.find((item) => item.id === currentAction.value)?.label ?? '待机')
const statusCopy = computed(() => fallback.value ? '资源缺失，已回退到待机' : paused.value ? '播放已暂停' : '动作播放中')

function selectAction(action: PetAction) {
  currentAction.value = action
  paused.value = false
}

function reset() {
  currentAction.value = 'idle'
  paused.value = false
  mouthMode.value = 'closed'
}
</script>

<template>
  <main class="workspace">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">CP</span>
        <div>
          <p class="eyebrow">DESKTOP PET / RENDER LAB</p>
          <h1>Canvas Pet Lab</h1>
        </div>
      </div>
      <div class="topbar-meta">
        <span class="status-dot" />
        <span>本地预览</span>
        <span class="version">v0.1</span>
      </div>
    </header>

    <section class="content-grid">
      <aside class="panel action-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">ACTION MAP</p>
            <h2>动作状态</h2>
          </div>
          <span class="count">10</span>
        </div>
        <div class="action-list">
          <button
            v-for="item in actions"
            :key="item.id"
            class="action-button"
            :class="[{ active: currentAction === item.id }, `tone-${item.tone}`]"
            type="button"
            @click="selectAction(item.id)"
          >
            <span class="action-swatch" />
            <span>{{ item.label }}</span>
            <span class="action-key">{{ item.id }}</span>
          </button>
        </div>
        <button class="reset-button" type="button" @click="reset">
          <span>↺</span>
          重置预览
        </button>
      </aside>

      <section class="stage-section">
        <div class="stage-toolbar">
          <div>
            <p class="eyebrow">LIVE PREVIEW</p>
            <h2>角色渲染画布</h2>
          </div>
          <div class="stage-actions">
            <button class="icon-button" type="button" :aria-label="paused ? '继续播放' : '暂停播放'" @click="paused = !paused">
              {{ paused ? '▶' : 'Ⅱ' }}
            </button>
            <span class="frame-readout">FRAME {{ String(currentFrame + 1).padStart(2, '0') }} / 04</span>
          </div>
        </div>
        <div class="stage">
          <div class="stage-grid" />
          <div class="stage-label">CANVAS / 2D CONTEXT</div>
          <PetCanvas
            :action="currentAction"
            :mouth-mode="mouthMode"
            :manifest="manifest"
            :paused="paused"
            @snapshot="(snapshot) => { currentFrame = snapshot.framePosition; fallback = snapshot.usingFallback }"
          />
          <div class="stage-floor" />
        </div>
        <div class="stage-caption">
          <span class="live-line" />
          <span>{{ statusCopy }}</span>
          <span class="caption-spacer" />
          <span class="mono">{{ currentAction }}</span>
        </div>
      </section>

      <aside class="panel inspector-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">INSPECTOR</p>
            <h2>当前状态</h2>
          </div>
          <span class="inspector-icon">✦</span>
        </div>
        <div class="state-card">
          <span class="state-kicker">ACTIVE ACTION</span>
          <strong>{{ currentLabel }}</strong>
          <span class="mono">action.{{ currentAction }}</span>
        </div>
        <label class="control-label" for="fps">播放速度 <span>{{ fps }} FPS</span></label>
        <input id="fps" v-model.number="fps" class="range" type="range" min="2" max="18" step="1">
        <div class="range-scale"><span>2</span><span>18</span></div>

        <div class="divider" />
        <p class="control-label">口型状态</p>
        <div class="segmented">
          <button v-for="mode in ['closed', 'half-open', 'open']" :key="mode" type="button" :class="{ active: mouthMode === mode }" @click="mouthMode = mode as typeof mouthMode">
            {{ mode === 'closed' ? '闭合' : mode === 'half-open' ? '半开' : '张开' }}
          </button>
        </div>

        <div class="divider" />
        <div class="resource-row">
          <span class="resource-icon">◈</span>
          <div>
            <strong>占位资源</strong>
            <span>Sprite manifest · ready</span>
          </div>
          <span class="ready">READY</span>
        </div>
        <div class="resource-row muted">
          <span class="resource-icon">＋</span>
          <div>
            <strong>真实角色资源</strong>
            <span>等待导入 PNG / SpriteSheet</span>
          </div>
          <span class="pending">PENDING</span>
        </div>
      </aside>
    </section>
  </main>
</template>
