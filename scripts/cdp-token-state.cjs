const wsUrl='ws://127.0.0.1:9222/devtools/page/7463270712EF2B520E2D7FA852934D35';
const ws=new WebSocket(wsUrl); let id=0; const pending=new Map();
function send(method,params={}){const msgId=++id; ws.send(JSON.stringify({id:msgId,method,params})); return new Promise((resolve,reject)=>pending.set(msgId,{resolve,reject}));}
ws.addEventListener('open',async()=>{
 await send('Runtime.enable');
 const expr=`(async()=>{
   const token=document.querySelector('.rtc-manual-token textarea')?.value || '';
   return JSON.stringify({tokenLength:token.length,prefix:token.slice(0,12),activeButtons:[...document.querySelectorAll('button')].map(b=>({text:b.innerText.trim(),disabled:b.disabled})).filter(x=>x.text.includes('官方 SDK')||x.text.includes('停止'))});
 })()`;
 const r=await send('Runtime.evaluate',{expression:expr,returnByValue:true});
 console.log(r.result.value); ws.close(); process.exit(0);
});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data); if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}});
setTimeout(()=>process.exit(2),15000);
