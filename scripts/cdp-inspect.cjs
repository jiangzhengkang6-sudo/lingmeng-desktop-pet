const wsUrl = process.argv[2];
const ws = new WebSocket(wsUrl);
let id = 0;
const pending = new Map();
const events=[];
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
  await new Promise(r=>setTimeout(r,2000));
  const expr = `JSON.stringify({
    href: location.href,
    bodyLength: document.body?.innerText?.length || 0,
    appHtml: document.querySelector('#app')?.innerHTML?.slice(0,1000),
    buttons:[...document.querySelectorAll('button')].slice(0,20).map(b=>b.innerText),
    errors: window.__errors || []
  })`;
  const result = await send('Runtime.evaluate',{expression:expr,returnByValue:true,timeout:10000});
  console.log(JSON.stringify({events, eval:result.result.value},null,2));
  ws.close(); process.exit(0);
});
ws.addEventListener('message', (event)=>{
 const msg=JSON.parse(event.data);
 if(msg.id && pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id); if(msg.error)p.reject(new Error(JSON.stringify(msg.error))); else p.resolve(msg.result);}
 if(msg.method==='Runtime.exceptionThrown'||msg.method==='Log.entryAdded'||msg.method==='Console.messageAdded') events.push(msg.params);
});
setTimeout(()=>process.exit(2),15000);
