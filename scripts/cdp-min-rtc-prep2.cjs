const fs=require('fs'),os=require('os'),path=require('path');
const token=fs.readFileSync(path.join(os.tmpdir(),'rtc-manual-token.txt'),'utf8').trim();
const expr=`(async()=>{
 const mod=await import('/node_modules/.vite/deps/@volcengine_rtc.js');
 const SDK=mod.default;
 const appId='6aa0f9442c260501e430e2c0';
 const roomId='desktop-pet-identity';
 const userId='desktop-owner';
 const token=${JSON.stringify(token)};
 window.__rtcMinimal2={events:[]};
 const engine=SDK.createEngine(appId);
 window.__rtcMinimal2.engine=engine;
 const log=(...a)=>window.__rtcMinimal2.events.push(a.map(x=>typeof x==='object'?JSON.stringify(x):String(x)).join(' '));
 engine.on(SDK.events.onConnectionStateChanged, e=>log('connection',JSON.stringify(e)));
 engine.on(SDK.events.onError, e=>log('error',JSON.stringify(e)));
 engine.on(SDK.events.onRoomStateChanged, e=>log('room',JSON.stringify(e)));
 engine.on(SDK.events.onUserJoined, e=>log('user-joined',JSON.stringify(e)));
 try{
   await engine.joinRoom(token, roomId, {userId, extraInfo:JSON.stringify({call_scene:'minimal-token-test-2'})}, {
     isAutoPublish:false,
     isAutoSubscribeAudio:true,
     roomProfileType:SDK.RoomProfileType.chat
   });
   log('join-returned-ok');
 }catch(e){ log('join-threw', String(e && (e.message||e.code||e))); }
 await new Promise(r=>setTimeout(r,12000));
 return JSON.stringify({events:window.__rtcMinimal2.events},null,2);
})()`;
fs.writeFileSync(path.join(os.tmpdir(),'rtc-min-expr2.txt'),expr,'utf8');
