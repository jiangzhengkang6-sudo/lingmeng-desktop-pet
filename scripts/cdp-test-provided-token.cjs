const fs=require('fs'),os=require('os'),path=require('path');
const token=fs.readFileSync(path.join(os.tmpdir(),'rtc-manual-token.txt'),'utf8').trim();
const ws=new WebSocket('ws://127.0.0.1:9222/devtools/page/7463270712EF2B520E2D7FA852934D35');
let id=0; const pending=new Map();
function send(method,params={}){const msgId=++id; ws.send(JSON.stringify({id:msgId,method,params})); return new Promise((resolve,reject)=>pending.set(msgId,{resolve,reject}));}
ws.addEventListener('open',async()=>{
 await send('Runtime.enable');
 const expr=`(async()=>{
  const token=${JSON.stringify(token)};
  // Ensure fresh session exists; if the page currently has none, click start.
  if(!document.body.innerText.includes('任务 ID：')) {
    const start=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('启动验证会话'));
    if(start && !start.disabled) start.click();
    for(let i=0;i<30;i++){await new Promise(r=>setTimeout(r,500)); if(document.body.innerText.includes('任务 ID：')) break;}
  }
  const box=[...document.querySelectorAll('textarea')].find(t=>t.placeholder.includes('临时 Token'));
  if(box){
    const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(box,token);
    box.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:token}));
    box.dispatchEvent(new Event('change',{bubbles:true}));
  }
  const stopSdk=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('停止官方 SDK'));
  if(stopSdk && !stopSdk.disabled){stopSdk.click(); await new Promise(r=>setTimeout(r,3000));}
  const sdk=[...document.querySelectorAll('button')].find(b=>b.innerText.includes('官方 SDK 加入并发麦克风'));
  if(sdk && !sdk.disabled) sdk.click();
  await new Promise(r=>setTimeout(r,15000));
  const text=document.body.innerText;
  const si=text.indexOf('RTC 声纹验证会话');
  return JSON.stringify({
    task:(text.match(/任务 ID：\s*([a-zA-Z0-9_-]+)/)||[])[1]||null,
    boxLength:box?box.value.length:0,
    tokenLength:token.length,
    tokenPrefix:token.slice(0,12),
    clicked:!!sdk,
    excerpt:text.slice(si,si+1200)
  });
 })()`;
 const r=await send('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true,timeout:40000});
 console.log(r.result.value||JSON.stringify(r));
 ws.close();process.exit(0);
});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}});
setTimeout(()=>process.exit(2),45000);
