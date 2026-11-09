<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

type OptionObject = {
  value: string
  label: string
  tag?: string
  disabled?: boolean
}
type OptionInput = string | OptionObject
type Option = OptionObject & { tagLabel: string }

const props = withDefaults(defineProps<{
  modelValue?: string
  options: OptionInput[]
  placeholder?: string
  showTags?: boolean
  disabled?: boolean
  size?: 'sm' | 'md' | 'lg'
  menuWidth?: number
  ariaLabel?: string
  accentColor?: string
  surfaceColor?: string
  highlightColor?: string
  textColor?: string
}>(), {
  modelValue: '',
  placeholder: '请选择',
  showTags: true,
  disabled: false,
  size: 'md',
  menuWidth: 190,
  ariaLabel: '选择器',
  accentColor: '#67e8f9',
  surfaceColor: 'rgba(10, 14, 28, .96)',
  highlightColor: 'rgba(34, 211, 238, .22)',
  textColor: '#e5f7ff',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string, option: Option]
}>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const list = ref<HTMLElement | null>(null)
const hoverIndex = ref<number | null>(null)
const keyboardIndex = ref<number | null>(null)

const normalizedOptions = computed<Option[]>(() => props.options.map((item) => {
  const option = typeof item === 'string'
    ? { value: item, label: item, tag: '', disabled: false }
    : {
      value: item.value,
      label: item.label,
      tag: item.tag ?? '',
      disabled: item.disabled ?? false,
    }
  return { ...option, tagLabel: option.tag ?? '' }
}))

const selectedIndex = computed(() =>
  normalizedOptions.value.findIndex((item) => item.value === props.modelValue),
)
const selectedOption = computed(() =>
  selectedIndex.value >= 0 ? normalizedOptions.value[selectedIndex.value] : null,
)
const rowHeight = computed(() => {
  if (props.size === 'sm') return 28
  if (props.size === 'lg') return 42
  return 34
})
const chipHeight = computed(() => {
  if (props.size === 'sm') return 30
  if (props.size === 'lg') return 46
  return 36
})
const pillStyle = computed(() => ({
  height: `${rowHeight.value}px`,
  transform: `translateY(${
    (hoverIndex.value ?? (selectedIndex.value >= 0 ? selectedIndex.value : 0))
    * (rowHeight.value + 1)
  }px)`,
  opacity: hoverIndex.value === null ? 0 : 1,
}))

function closeMenu() {
  open.value = false
  hoverIndex.value = null
  keyboardIndex.value = null
}

function toggleMenu() {
  if (props.disabled) return
  if (open.value) {
    closeMenu()
    return
  }
  open.value = true
  keyboardIndex.value = selectedIndex.value >= 0 ? selectedIndex.value : 0
}

function choose(option: Option, index: number) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value, option)
  hoverIndex.value = index
  closeMenu()
}

function onOptionEnter(index: number) {
  hoverIndex.value = index
}

function onListLeave() {
  hoverIndex.value = null
}

function focusOption(index: number) {
  const total = normalizedOptions.value.length
  const next = (index + total) % total
  keyboardIndex.value = next
  hoverIndex.value = next
  void nextTick(() => {
    list.value?.children[next]?.querySelector('button')?.focus()
  })
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) open.value = true
    const start = keyboardIndex.value ?? selectedIndex.value
    focusOption(event.key === 'ArrowDown' ? start + 1 : start - 1)
  }
  if (event.key === 'Escape') closeMenu()
}

function onDocumentPointerDown(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) closeMenu()
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointerDown))
</script>

<template>
  <div
    ref="root"
    class="glide-select"
    :class="[`glide-select--${size}`, { 'glide-select--open': open, 'glide-select--disabled': disabled }]"
    :style="{
      '--gs-accent': accentColor,
      '--gs-surface': surfaceColor,
      '--gs-highlight': highlightColor,
      '--gs-text': textColor,
      '--gs-chip-height': `${chipHeight}px`,
      '--gs-row': `${rowHeight}px`,
      '--gs-menu-width': `${menuWidth}px`,
    }"
  >
    <button
      ref="trigger"
      class="glide-select__trigger"
      type="button"
      :disabled="disabled"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggleMenu"
      @keydown="onTriggerKeydown"
    >
      <span class="glide-select__label" :class="{ 'is-empty': !selectedOption }">
        {{ selectedOption?.label ?? placeholder }}
      </span>
      <span class="glide-select__chevron" aria-hidden="true">⌄</span>
    </button>

    <transition name="glide-pop">
      <div
        v-if="open"
        class="glide-select__menu"
      >
        <div
          ref="list"
          class="glide-select__list"
          role="listbox"
          :aria-label="ariaLabel"
          @mouseleave="onListLeave"
        >
          <span class="glide-select__pill" aria-hidden="true" :style="pillStyle" />
          <template v-for="(option, index) in normalizedOptions" :key="option.value">
            <button
              class="glide-select__option"
              type="button"
              role="option"
              :aria-selected="index === selectedIndex"
              :disabled="option.disabled"
              @click="choose(option, index)"
              @mouseenter="onOptionEnter(index)"
            >
              <span class="glide-select__name">{{ option.label }}</span>
              <span v-if="showTags && option.tagLabel" class="glide-select__tag">{{ option.tagLabel }}</span>
              <span class="glide-select__check" aria-hidden="true">✓</span>
            </button>
          </template>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.glide-select {
  position: relative;
  width: 100%;
  color: var(--gs-text);
}

.glide-select__trigger,
.glide-select__option {
  border: 1px solid rgba(103, 232, 249, .2);
  font: inherit;
  color: var(--gs-text);
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .16s ease;
}

.glide-select__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: var(--gs-chip-height);
  padding: 0 10px;
  border-radius: 11px;
  background: color-mix(in srgb, var(--gs-surface) 88%, transparent);
  box-shadow: inset 0 0 18px rgba(34, 211, 238, .06);
}

.glide-select__trigger:hover,
.glide-select--open .glide-select__trigger {
  border-color: color-mix(in srgb, var(--gs-accent) 65%, transparent);
  background: color-mix(in srgb, var(--gs-highlight) 58%, var(--gs-surface));
}

.glide-select__trigger:active { transform: scale(.98); }
.glide-select__trigger:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.glide-select__label {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.glide-select__label.is-empty { opacity: .58; }

.glide-select__chevron {
  flex: 0 0 auto;
  margin-left: 8px;
  color: color-mix(in srgb, var(--gs-text) 65%, transparent);
  transition: transform .2s ease;
}
.glide-select--open .glide-select__chevron { transform: rotate(180deg); }

.glide-select__menu {
  position: absolute;
  top: calc(100% + 7px);
  left: 0;
  z-index: 80;
  width: var(--gs-menu-width);
  min-width: 100%;
  padding: 4px;
  border: 1px solid rgba(103, 232, 249, .24);
  border-radius: 13px;
  background: var(--gs-surface);
  box-shadow:
    0 18px 44px rgba(0, 0, 0, .42),
    0 0 28px rgba(34, 211, 238, .12);
  backdrop-filter: blur(20px);
  transform-origin: top left;
}

.glide-select__list {
  position: relative;
  display: grid;
  gap: 1px;
}

.glide-select__pill {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  border-radius: 8px;
  background: var(--gs-highlight);
  box-shadow: inset 0 0 14px rgba(255, 255, 255, .05);
  pointer-events: none;
  transition: transform .22s ease, opacity .15s ease;
}

.glide-select__option {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--gs-row);
  padding: 0 9px;
  border-color: transparent;
  border-radius: 8px;
  background: transparent;
}

.glide-select__option:hover,
.glide-select__option[aria-selected='true'] {
  border-color: transparent;
}

.glide-select__option:focus-visible {
  outline: 1px solid var(--gs-accent);
  outline-offset: 2px;
}

.glide-select__option:disabled {
  opacity: .38;
  cursor: not-allowed;
}

.glide-select__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.glide-select__tag {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--gs-text) 55%, transparent);
  font-size: 10px;
}

.glide-select__check {
  flex: 0 0 auto;
  color: var(--gs-accent);
  opacity: 0;
}
.glide-select__option[aria-selected='true'] .glide-select__check { opacity: 1; }

.glide-pop-enter-active,
.glide-pop-leave-active {
  transition: opacity .18s ease, transform .18s ease;
}
.glide-pop-enter-from,
.glide-pop-leave-to {
  opacity: 0;
  transform: scale(.96) translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .glide-select *,
  .glide-select *::before,
  .glide-select *::after {
    transition: none !important;
  }
}
</style>
