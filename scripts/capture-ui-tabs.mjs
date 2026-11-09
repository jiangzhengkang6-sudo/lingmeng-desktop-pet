import { writeFile, mkdir } from 'node:fs/promises'
import { join } from 'node:path'

const targets = await (await fetch('http://127.0.0.1:9223/json/list')).json()
const target = targets.find((item) => item.url.startsWith('http://127.0.0.1:5174'))
if (!target) throw new Error('未找到 Vite 页面目标')

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

const outDir = join(process.env.TEMP, 'ui-tab-captures')
await mkdir(outDir, { recursive: true })
const tabs = [
  ['chat', 1],
  ['voice', 2],
  ['resource', 3],
  ['knowledge', 4],
  ['system', 5],
]

for (const [name, index] of tabs) {
  await send('Runtime.evaluate', {
    expression: `document.querySelectorAll('.ui-tabs__item')[${index}].click()`,
  })
  await new Promise((resolve) => setTimeout(resolve, 800))
  const screenshot = await send('Page.captureScreenshot', { format: 'png' })
  const output = join(outDir, `ui-${name}.png`)
  await writeFile(output, Buffer.from(screenshot.data, 'base64'))
  console.log(output)
}

ws.close()
