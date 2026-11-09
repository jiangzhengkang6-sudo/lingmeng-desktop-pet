import { spawn } from 'node:child_process'

const devProcess = spawn('npm', ['run', 'dev'], { shell: true })
await new Promise((resolve) => setTimeout(resolve, 4000))

const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const profile = `${process.env.TEMP}\\edge-pref-fallback-profile`
const edgeProcess = spawn(edge, [
  '--headless=new',
  '--remote-debugging-port=9225',
  `--user-data-dir=${profile}`,
  '--window-size=1440,900',
  'http://127.0.0.1:5174/',
], {})
await new Promise((resolve) => setTimeout(resolve, 4000))

const targets = await (await fetch('http://127.0.0.1:9225/json/list')).json()
const target = targets.find((item) => item.url.startsWith('http://127.0.0.1:5174'))
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
await new Promise((resolve) => { ws.addEventListener('open', resolve, { once: true }) })
await send('Page.enable')
await send('Runtime.enable')

await send('Runtime.evaluate', { expression: `
  localStorage.setItem('anime-agent-agent-language', 'klingon');
  localStorage.setItem('anime-agent-tts-language', 'klingon');
  localStorage.setItem('anime-agent-asr-language', 'klingon');
  localStorage.setItem('anime-agent-voice-persona', 'not-exist');
` })
await send('Page.reload', { ignoreCache: true })
await new Promise((resolve) => setTimeout(resolve, 2500))

const result = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `
    ({
      agentLabel: document.querySelector('.agent-panel .glide-select__label')?.textContent,
      ttsLabel: document.querySelector('.tts-panel .glide-select__label')?.textContent,
      asrLabel: document.querySelector('.asr-panel .glide-select__label')?.textContent,
      personaSelectValue: document.querySelector('.persona-controls select')?.value,
    })
  `,
})
console.log(JSON.stringify(result.result.value, null, 2))

ws.close()
edgeProcess.kill()
devProcess.kill()
