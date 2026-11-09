const wsUrl = process.argv[2];
const expression = process.argv[3] || 'location.href';
const ws = new WebSocket(wsUrl);
let id = 0;
const pending = new Map();
function send(method, params={}) {
  const msgId = ++id;
  ws.send(JSON.stringify({id:msgId,method,params}));
  return new Promise((resolve,reject)=>pending.set(msgId,{resolve,reject}));
}
ws.addEventListener('open', async () => {
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Console.enable');
  await send('Network.enable');
  const result = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    timeout: 10000,
  });
  console.log(JSON.stringify(result.result || result.error || result, null, 2));
  ws.close();
  process.exit(0);
});
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const {resolve,reject} = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error))); else resolve(msg.result);
  }
});
ws.addEventListener('error', (event) => { console.error('WS_ERROR', event.message || event); process.exit(1); });
setTimeout(() => { console.error('CDP timeout'); process.exit(2); }, 15000);
