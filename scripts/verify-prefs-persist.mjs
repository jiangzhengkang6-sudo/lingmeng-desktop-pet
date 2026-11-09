import { spawn } from 'node:child_process'

const devProcess = spawn('npm', ['run', 'dev'], { shell: true })
await new Promise((resolve) => setTimeout(resolve, 4000))

const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const profile = `${process.env.TEMP}\\edge-pref-persist-profile`
const edgeProcess = spawn(edge, [
  '--headless=new',
  '--remote-debugging-port=9224',
  `--user-data-dir=${profile}`,
  '--window-size=1440,900',
  'http://127.0.0.1:5174/',
], { detached: false })

await new Promise((resolve) => setTimeout(resolve, 4000))

const targets = await (await fetch('http://127.0.0.1:9224/json/list')).json()
const target = targets.find((item) => item.url.startsWith('http://127.0.0.1:5174'))
if (!target) throw new Error('未找到 Vite 页面')

const ws = new WebSocket(target.webSocketDebuggerUrl)
let messageId = 0
const pending = new Map()

function send(method, params = {}) {
  const id = ++messageId
  ws.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
  }
})

await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true })
  ws.addEventListener('error', reject, { once: true })
})
await send('Page.enable')
await send('Runtime.enable')

function evaluate(expression, awaitPromise = true) {
  return send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true })
}

// 1. 模拟用户切换：对话页日语、TTS 英语、ASR 日语、声线切到“雷厉千金”
await evaluate(`
  localStorage.setItem('anime-agent-agent-language', 'ja-JP');
  localStorage.setItem('anime-agent-tts-language', 'en-US');
  localStorage.setItem('anime-agent-asr-language', 'ja-JP');
  localStorage.setItem('anime-agent-voice-persona', 'decisive-princess-ja');
`)

// 2. 真实刷新页面，等价于重启应用后的重新加载
await send('Page.reload', { ignoreCache: true })
await new Promise((resolve) => setTimeout(resolve, 2500))

// 3. 读取界面中各组件恢复后的值
const result = await evaluate(`
  ({
    agent: localStorage.getItem('anime-agent-agent-language'),
    tts: localStorage.getItem('anime-agent-tts-language'),
    asr: localStorage.getItem('anime-agent-asr-language'),
    persona: localStorage.getItem('anime-agent-voice-persona'),
  })
`)

console.log(JSON.stringify(result.result.value, null, 2))

// 4. 写入一个非法脏值，确认重启后会被安全忽略而非崩溃
await evaluate(`
  localStorage.setItem('anime-agent-agent-language', 'klingon');
  localStorage.setItem('anime-agent-voice-persona', 'not-exist');
`)
await send('Page.reload', { ignoreCache: true })
await new Promise((resolve) => setTimeout(resolve, 2500))
const fallback = await evaluate(`
  ({
    agent: localStorage.getItem('anime-agent-agent-language'),
    persona: localStorage.getItem('anime-agent-voice-persona'),
  })
`)
console.log('invalid-value test:', JSON.stringify(fallback.result.value))

ws.close()
edgeProcess.kill()
devProcess.kill()
