from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pathlib import Path
from copy import deepcopy

src = Path(r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报.pptx')
out = src.with_name('二次元桌宠智能体项目汇报-详实版.pptx')
prs = Presentation(src)

FONT = 'Microsoft YaHei'
DARK = RGBColor(64, 64, 64)
MID = RGBColor(102, 102, 102)
PINK = RGBColor(204, 0, 153)
ROSE = RGBColor(243, 87, 100)
WHITE = RGBColor(255,255,255)

# text replacements by (slide index, shape index in slide.shapes 1-based)
replacements = {
(1,8): ['v0.4 阶段汇报'],
(1,13): [
'v0.4 功能实现与联调进展',
'Tauri × Godot × FastAPI',
'Qwen × MiniMax × 火山RTC'
],
(2,6): ['汇报目录'],
(2,7): [
'01 项目背景与目标定位',
'02 总体架构与技术选型',
'03 核心功能与当前实现',
'04 关键问题、安全边界与解决方案',
'05 测试验证与数据结果',
'06 项目亮点与阶段成果',
'07 当前风险与下一步计划',
'08 演示路径与总结'
],
(3,8): ['项目介绍'],
(3,9): [
'项目定位：运行在 Windows 桌面的二次元 AI 伙伴，而不是单一聊天窗口。',
'当前版本：已形成 Tauri 控制台 + FastAPI 本地网关 + Godot 桌宠渲染的可安装桌面应用。',
'交互方式：文本、手动录音、连续语音并存；支持中文、日语、英语识别和多音色 TTS 回复。',
'核心能力：角色动作、语音对话、本地时间工具、受控桌面能力、记忆/工具框架、调试历史、RTC 声纹验证。',
'阶段目标：先打通“可看、可听、可说、可控、可追溯”的闭环，再逐步增强长期记忆与主人权限。'
],
(4,6): ['用户痛点'],
(4,7): [
'传统桌宠只有预设动画，无法理解语义，也不能执行桌面任务。',
'通用助手缺少人格、角色形象和持续陪伴感，交互停留在对话框。',
'纯云端助手难以感知本地环境，工具执行缺少白名单、审批和审计。',
'语音、动作、权限、记忆分散在多个系统中，集成复杂且失败点不透明。'
],
(4,9): ['项目机会'],
(4,10): [
'把“可见的角色形象、可听的语音、可控的本地能力”合并为一个桌面智能体。',
'用 Godot 游戏级渲染补足动作表现力，用本地网关统一适配 ASR、TTS、LLM 与 RTC。',
'以主人身份和工具权限形成安全边界，让模型只能在授权范围内行动。',
'通过阶段化调试历史和状态反馈，将复杂链路变成可观察、可验收的产品。'
],
(5,14): ['核心技术栈：Tauri 2 / Vue 3 / Godot 4 / FastAPI / Qwen / 豆包 ASR / MiniMax TTS / 火山 RTC / SQLite'],
(5,15): [
'本地优先：网关、配置、工具审计、调试历史和桌面状态运行在用户电脑。',
'云端增强：实时语音识别、语音合成、文本大模型和声纹识别按需调用。',
'渲染解耦：Agent 只输出语义动作，Godot 根据统一动作协议播放 SpriteSheet。',
'安全闭环：工具请求先过 Schema、白名单、身份与审批，再执行并记录结果。'
],
(6,3): ['语音与多语言'],
(6,4): [
'豆包 SAUC WebSocket 完成实时转写；MiniMax 返回多语言音频。',
'支持中文、日语、英语；连续对话支持本地唤醒词“小赤红”。',
'Manual 模式可点击录音，Automatic 模式由 VAD 自动断句。',
'ASR final、Agent、TTS、桌宠动作均有独立状态，失败时可定位到具体阶段。'
],
(6,7): ['桌宠模型系统'],
(6,8): [
'Godot 负责透明窗口、SpriteSheet 切帧、动作循环和口型表现。',
'Tauri 写入 preview.json，同步 listening / thinking / speaking / idle 等状态。',
'支持傲娇、温柔、开心、害羞、拒绝等角色表现，并保留 Canvas 占位兜底。',
'资源 manifest 校验帧宽、帧高、列数、锚点和文件路径，降低素材不规范导致的抖动。'
],
(6,11): ['人格、记忆与工具'],
(6,12): [
'人格/记忆：角色提示词、候选确认与 SQLite 本地存储。',
'工具：get_time 稳定接入；桌面能力采用白名单和审批。',
'身份：RTC VoiceChat + VoicePrint 声纹验证仍在联调。'
],
(7,8): ['问题与挑战'],
(7,9): [
'语音链路长：麦克风采集、ASR、Agent、TTS、音频播放任一环失败都会影响体验。',
'实时反馈难：partial/final 重复、麦克风抢占和播放时机容易造成重复提交。',
'桌面安全要求高：模型不能直接获得 Shell 或任意文件访问权。',
'角色素材不标准：SpriteSheet 帧数、透明边距、锚点不一致会造成动作跳动。',
'RTC 声纹涉及 AppId、AppKey、Token、RoomId、UserId、StartVoiceChat 与 RTS 回调，云端配置耦合度高。'
],
(9,9): ['测试与验证'],
(9,10): [
'前端自动化：34 个测试文件、120 个 Vitest 测试通过。',
'后端自动化：143 个 Pytest 测试通过，覆盖 ASR 协议、Agent、RTC Token、工具和身份事件。',
'接口实测：豆包 ASR 已返回真实识别文本；MiniMax TTS 已返回真实音频；get_time 本地工具 50ms 级返回。',
'安装验证：MSI 可安装启动，健康检查、RTC bridge、场景文件和运行时 .env 已可独立排查。',
'当前未闭环：官方 RTC SDK 入房与 RTS 主人声纹回调仍处于云端配置联调阶段。'
],
(10,7): ['项目亮点'],
(10,8): [
'1. 游戏级角色渲染：Godot 承担桌宠动画，突破普通聊天 UI 的表现边界。',
'2. 四层解耦架构：前端、本地网关、云端模型、桌面渲染职责清晰，可替换供应商。',
'3. 语音-语义-动作闭环：ASR 文本驱动 Agent，Agent 动作协议驱动桌宠状态。',
'4. 安全工具模型：模型不直接操作系统，所有能力通过受控工具、身份与审计执行。',
'5. 本地可观测：调试历史、健康检查、RTC bridge、接口状态和错误提示支持快速定位。',
'6. 可安装交付：PyInstaller + Tauri 打包为 Windows MSI，具备持续迭代基础。'
],
(12,2): ['感谢聆听｜二次元桌宠智能体 v0.4']
}

def set_text(shape, paragraphs, size=None, color=None, bold=None):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Pt(2)
    tf.margin_right = Pt(2)
    tf.margin_top = Pt(1)
    tf.margin_bottom = Pt(1)
    for idx, text in enumerate(paragraphs):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = text
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(5)
        p.line_spacing = 1.08
        run = p.runs[0] if p.runs else p.add_run()
        run.font.name = FONT
        if size: run.font.size = Pt(size)
        if color: run.font.color.rgb = color
        if bold is not None: run.font.bold = bold

# Apply mapped replacements, adapting font size based on amount of text.
for (slide_idx, shape_idx), lines in replacements.items():
    shape = prs.slides[slide_idx-1].shapes[shape_idx-1]
    if not hasattr(shape, 'text_frame'):
        continue
    longest = max((len(x) for x in lines), default=0)
    if slide_idx == 1:
        size = 16 if shape_idx == 8 else 13
        color, bold = PINK, True
    elif slide_idx == 6 and shape_idx == 12:
        size, color, bold = 9.5, MID, True
    elif slide_idx == 12:
        size, color, bold = 20, ROSE, True
        shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    elif shape_idx in (6,9,14,17) and len('\n'.join(lines)) < 30:
        size, color, bold = 20, DARK, True
    else:
        size = 13
        if longest > 48: size = 11
        if sum(map(len,lines)) > 320: size = 10
        color, bold = MID, True
    set_text(shape, lines, size=size, color=color, bold=bold)

# Slides 8 and 11 keep their visual design; enrich the text that already exists
# inside their grouped quotation panels instead of adding overlays.
def set_group_lines(slide_idx, group_idx, group_shape_idx, lines, size=13):
    group = prs.slides[slide_idx - 1].shapes[group_idx - 1]
    shape = group.shapes[group_shape_idx - 1]
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Pt(1)
    tf.margin_right = Pt(1)
    tf.margin_top = Pt(1)
    tf.margin_bottom = Pt(1)
    for idx, text in enumerate(lines):
        paragraph = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        paragraph.text = text
        paragraph.alignment = PP_ALIGN.LEFT
        paragraph.space_after = Pt(2)
        paragraph.line_spacing = 1.0
        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
        run.font.name = '幼圆'
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.color.rgb = RGBColor(127, 127, 127)

set_group_lines(8, 5, 4, [
    'Phase 0：模型与资源验证',
    'Phase 1：语音 Agent 动作闭环',
    'Phase 2：身份记忆权限审批',
    'Phase 3：连续对话桌面体验'
])
set_group_lines(11, 4, 4, [
    'RTC 入房与声纹回调',
    '配置向导与配置检查',
    '白名单授权与提醒体验',
    '语音动作延迟重试优化'
])

# Give the lower-right content block on slide 6 enough room for its three lines.
slide_six_tools = prs.slides[5].shapes[11]
slide_six_tools.top = Inches(5.22)
slide_six_tools.height = Inches(1.55)

# Center thank-you text.
shape=prs.slides[11].shapes[1]
shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

prs.save(out)
print(out)
print('slides', len(prs.slides))
