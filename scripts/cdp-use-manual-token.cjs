const fs=require('fs');
const os=require('os');
const path=require('path');
const wsUrl='ws://127.0.0.1:9222/devtools/page/7463270712EF2B520E2D7FA852934D35';
const token=fs.readFileSync(path.join(os.tmpdir(),'rtc-manual-token.txt'),'utf8').trim();
const ws=new WebSocket(wsUrl);
let id=0; const pending=new Map();
function send(method,params={}){const msgId=++id; ws.send(JSON.stringify({id:msgId,method,params})); return new Promise((resolve,reject)=>pending.set(msgId,{resolve,reject}));}
ws.addEventListener('open',async()=>{
 await send('Runtime.enable');
 const expr = `(async()=>{
 const token=${JSON.stringify(token)};
 let start=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('启动验证会话'));
 if(start&&!start.disabled) start.click();
 for(let i=0;i<30;i++){await new Promise(r=>setTimeout(r,500)); if(document.body.innerText.includes('任务 ID：')) break;}
 const box=[...document.querySelectorAll('textarea')].find(t=>t.placeholder.includes('临时 Token'));
 if(box){box.value=token; box.dispatchEvent(new Event('input',{bubbles:true})); box.dispatchEvent(new Event('change',{bubbles:true}));}
 await new Promise(r=>setTimeout(r,500));
 const sdk=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('官方 SDK 加入并发麦克风'));
 if(sdk&&!sdk.disabled) sdk.click();
 await new Promise(r=>setTimeout(r,12000));
 const text=document.body.innerText; const si=text.indexOf('RTC 声纹验证会话');
 return JSON.stringify({task:(text.match(/任务 ID：\\s*([a-zA-Z0-9_-]+)/)||[])[1]||null,hasTokenBox:Boolean(box),sdkClicked:Boolean(sdk),excerpt:text.slice(si,si+1600)});
 })()`;
 const result=await send('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true,timeout:30000});
 console.log(result.result.value); ws.close(); process.exit(0);
});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data); if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id); m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}});
setTimeout(()=>process.exit(2),40000);
