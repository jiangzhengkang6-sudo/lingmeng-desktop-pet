import { computed, ref } from 'vue';
import PetCanvas from './components/PetCanvas.vue';
const actions = [
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
];
const currentAction = ref('idle');
const mouthMode = ref('closed');
const paused = ref(false);
const fps = ref(8);
const currentFrame = ref(0);
const fallback = ref(false);
const manifest = computed(() => ({
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
}));
const currentLabel = computed(() => actions.find((item) => item.id === currentAction.value)?.label ?? '待机');
const statusCopy = computed(() => fallback.value ? '资源缺失，已回退到待机' : paused.value ? '播放已暂停' : '动作播放中');
function selectAction(action) {
    currentAction.value = action;
    paused.value = false;
}
function reset() {
    currentAction.value = 'idle';
    paused.value = false;
    mouthMode.value = 'closed';
}
const __VLS_ctx = {
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.main, __VLS_intrinsics.main)({
    ...{ class: "workspace" },
});
/** @type {__VLS_StyleScopedClasses['workspace']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.header, __VLS_intrinsics.header)({
    ...{ class: "topbar" },
});
/** @type {__VLS_StyleScopedClasses['topbar']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "brand" },
});
/** @type {__VLS_StyleScopedClasses['brand']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "brand-mark" },
});
/** @type {__VLS_StyleScopedClasses['brand-mark']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "topbar-meta" },
});
/** @type {__VLS_StyleScopedClasses['topbar-meta']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span)({
    ...{ class: "status-dot" },
});
/** @type {__VLS_StyleScopedClasses['status-dot']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "version" },
});
/** @type {__VLS_StyleScopedClasses['version']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "content-grid" },
});
/** @type {__VLS_StyleScopedClasses['content-grid']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.aside, __VLS_intrinsics.aside)({
    ...{ class: "panel action-panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['action-panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "panel-heading" },
});
/** @type {__VLS_StyleScopedClasses['panel-heading']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "count" },
});
/** @type {__VLS_StyleScopedClasses['count']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "action-list" },
});
/** @type {__VLS_StyleScopedClasses['action-list']} */ ;
for (const [item] of __VLS_vFor((__VLS_ctx.actions))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                return (__VLS_ctx.selectAction(item.id));
                // @ts-ignore
                [actions, selectAction,];
            } },
        key: (item.id),
        ...{ class: "action-button" },
        ...{ class: ([{ active: __VLS_ctx.currentAction === item.id }, `tone-${item.tone}`]) },
        type: "button",
    });
    /** @type {__VLS_StyleScopedClasses['action-button']} */ ;
    /** @type {__VLS_StyleScopedClasses['active']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span)({
        ...{ class: "action-swatch" },
    });
    /** @type {__VLS_StyleScopedClasses['action-swatch']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (item.label);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "action-key" },
    });
    /** @type {__VLS_StyleScopedClasses['action-key']} */ ;
    (item.id);
    // @ts-ignore
    [currentAction,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (__VLS_ctx.reset) },
    ...{ class: "reset-button" },
    type: "button",
});
/** @type {__VLS_StyleScopedClasses['reset-button']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "stage-section" },
});
/** @type {__VLS_StyleScopedClasses['stage-section']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "stage-toolbar" },
});
/** @type {__VLS_StyleScopedClasses['stage-toolbar']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "stage-actions" },
});
/** @type {__VLS_StyleScopedClasses['stage-actions']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (...[$event]) => {
            return (__VLS_ctx.paused = !__VLS_ctx.paused);
            // @ts-ignore
            [reset, paused, paused,];
        } },
    ...{ class: "icon-button" },
    type: "button",
    'aria-label': (__VLS_ctx.paused ? '继续播放' : '暂停播放'),
});
/** @type {__VLS_StyleScopedClasses['icon-button']} */ ;
(__VLS_ctx.paused ? '▶' : 'Ⅱ');
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "frame-readout" },
});
/** @type {__VLS_StyleScopedClasses['frame-readout']} */ ;
(String(__VLS_ctx.currentFrame + 1).padStart(2, '0'));
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "stage" },
});
/** @type {__VLS_StyleScopedClasses['stage']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div)({
    ...{ class: "stage-grid" },
});
/** @type {__VLS_StyleScopedClasses['stage-grid']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "stage-label" },
});
/** @type {__VLS_StyleScopedClasses['stage-label']} */ ;
const __VLS_0 = PetCanvas;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    ...{ 'onSnapshot': {} },
    action: (__VLS_ctx.currentAction),
    mouthMode: (__VLS_ctx.mouthMode),
    manifest: (__VLS_ctx.manifest),
    paused: (__VLS_ctx.paused),
}));
const __VLS_2 = __VLS_1({
    ...{ 'onSnapshot': {} },
    action: (__VLS_ctx.currentAction),
    mouthMode: (__VLS_ctx.mouthMode),
    manifest: (__VLS_ctx.manifest),
    paused: (__VLS_ctx.paused),
}, ...__VLS_functionalComponentArgsRest(__VLS_1));
let __VLS_5;
const __VLS_6 = {
    /** @type {typeof __VLS_5.snapshot} */
    onSnapshot: ((snapshot) => { __VLS_ctx.currentFrame = snapshot.framePosition; __VLS_ctx.fallback = snapshot.usingFallback; }),
};
var __VLS_3;
var __VLS_4;
__VLS_asFunctionalElement1(__VLS_intrinsics.div)({
    ...{ class: "stage-floor" },
});
/** @type {__VLS_StyleScopedClasses['stage-floor']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "stage-caption" },
});
/** @type {__VLS_StyleScopedClasses['stage-caption']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span)({
    ...{ class: "live-line" },
});
/** @type {__VLS_StyleScopedClasses['live-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
(__VLS_ctx.statusCopy);
__VLS_asFunctionalElement1(__VLS_intrinsics.span)({
    ...{ class: "caption-spacer" },
});
/** @type {__VLS_StyleScopedClasses['caption-spacer']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "mono" },
});
/** @type {__VLS_StyleScopedClasses['mono']} */ ;
(__VLS_ctx.currentAction);
__VLS_asFunctionalElement1(__VLS_intrinsics.aside, __VLS_intrinsics.aside)({
    ...{ class: "panel inspector-panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['inspector-panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "panel-heading" },
});
/** @type {__VLS_StyleScopedClasses['panel-heading']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "inspector-icon" },
});
/** @type {__VLS_StyleScopedClasses['inspector-icon']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "state-card" },
});
/** @type {__VLS_StyleScopedClasses['state-card']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "state-kicker" },
});
/** @type {__VLS_StyleScopedClasses['state-kicker']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
(__VLS_ctx.currentLabel);
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "mono" },
});
/** @type {__VLS_StyleScopedClasses['mono']} */ ;
(__VLS_ctx.currentAction);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "control-label" },
    for: "fps",
});
/** @type {__VLS_StyleScopedClasses['control-label']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
(__VLS_ctx.fps);
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "fps",
    ...{ class: "range" },
    type: "range",
    min: "2",
    max: "18",
    step: "1",
});
(__VLS_ctx.fps);
/** @type {__VLS_StyleScopedClasses['range']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "range-scale" },
});
/** @type {__VLS_StyleScopedClasses['range-scale']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.div)({
    ...{ class: "divider" },
});
/** @type {__VLS_StyleScopedClasses['divider']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "control-label" },
});
/** @type {__VLS_StyleScopedClasses['control-label']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "segmented" },
});
/** @type {__VLS_StyleScopedClasses['segmented']} */ ;
for (const [mode] of __VLS_vFor((['closed', 'half-open', 'open']))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                return (__VLS_ctx.mouthMode = mode);
                // @ts-ignore
                [currentAction, currentAction, currentAction, paused, paused, paused, currentFrame, currentFrame, mouthMode, mouthMode, mouthMode, manifest, fallback, statusCopy, currentLabel, fps, fps,];
            } },
        key: (mode),
        type: "button",
        ...{ class: ({ active: __VLS_ctx.mouthMode === mode }) },
    });
    /** @type {__VLS_StyleScopedClasses['active']} */ ;
    (mode === 'closed' ? '闭合' : mode === 'half-open' ? '半开' : '张开');
    // @ts-ignore
    [mouthMode,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.div)({
    ...{ class: "divider" },
});
/** @type {__VLS_StyleScopedClasses['divider']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "resource-row" },
});
/** @type {__VLS_StyleScopedClasses['resource-row']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "resource-icon" },
});
/** @type {__VLS_StyleScopedClasses['resource-icon']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "ready" },
});
/** @type {__VLS_StyleScopedClasses['ready']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "resource-row muted" },
});
/** @type {__VLS_StyleScopedClasses['resource-row']} */ ;
/** @type {__VLS_StyleScopedClasses['muted']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "resource-icon" },
});
/** @type {__VLS_StyleScopedClasses['resource-icon']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "pending" },
});
/** @type {__VLS_StyleScopedClasses['pending']} */ ;
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
