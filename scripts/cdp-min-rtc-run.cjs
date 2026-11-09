const fs=require('fs'),os=require('os'),path=require('path');
const expr=fs.readFileSync(path.join(os.tmpdir(),'rtc-min-expr.txt'),'utf8');
const ws=new WebSocket('ws://127.0.0.1:9222/devtools/page/7463270712EF2B520E2D7FA852934D35');
let id=0; const pending=new Map();
function send(method,params={}){const msgId=++id;ws.send(JSON.stringify({id:msgId,method,params}));return new Promise((resolve,reject)=>pending.set(msgId,{resolve,reject}));}
ws.addEventListener('open',async()=>{await send('Runtime.enable');const r=await send('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true,timeout:25000});console.log(r.result.value||JSON.stringify(r));ws.close();process.exit(0);});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}});
setTimeout(()=>process.exit(2),30000);
