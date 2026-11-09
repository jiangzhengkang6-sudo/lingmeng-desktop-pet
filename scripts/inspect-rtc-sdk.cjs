const fs=require('fs');
const s=fs.readFileSync('node_modules/@volcengine/rtc/index.esm.min.js','utf8');
for (const needle of ['INVALID_TOKEN','TOKEN_EXPIRED','b01','001','joinRoom(']) {
  console.log('\nNEEDLE', needle);
  let index=s.indexOf(needle), count=0;
  while(index>=0 && count<5){
    console.log(index, s.slice(Math.max(0,index-300), index+500));
    index=s.indexOf(needle,index+needle.length); count++;
  }
}
