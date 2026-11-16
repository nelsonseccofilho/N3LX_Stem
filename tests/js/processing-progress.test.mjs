import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
let resolveFinal;
let jsonStarted;
const jsonReady=new Promise(resolve=>jsonStarted=resolve);
const context=vm.createContext({console,Date, getLanguage:()=>"pt",onLanguageChange(){},
  document:{getElementById:()=>null},setInterval:()=>1,clearInterval(){},
  fetch:async()=>({ok:true,json:()=>{const pending=new Promise(resolve=>resolveFinal=resolve);jsonStarted();return pending;}}),
});
const source=fs.readFileSync(new URL("../../static/js/processingProgress.js",import.meta.url),"utf8").replace(/^import[^;]+;\r?\n/gm,"").replace(/^export /gm,"");
vm.runInContext(source+"\nglobalThis.api={queueChanged,current:()=>current,select:id=>selectedId=id};",context);
const api=context.api;
const running={job_id:"one",status:"separating",processing:{step:"drums",fraction:.42,steps:[]}};
await api.queueChanged({running,queued:[]});
assert.equal(api.current().processing.fraction,.42);
api.select("waiting");
await api.queueChanged({running,queued:[{job_id:"waiting",status:"queued"}]});
assert.equal(api.current().job_id,"waiting");
assert.equal(api.current().processing.steps.length,8);
assert.deepEqual(Array.from(api.current().processing.steps, step=>step.id).slice(3,6),["vocals","guitars","drums"]);
assert.equal(api.current().processing.fraction,null);
assert(api.current().processing.steps.every(step=>step.state==="pending"));
api.select(null);
await api.queueChanged({running,queued:[]});
const finishing=api.queueChanged({running:null,queued:[]});
await jsonReady;
await api.queueChanged({running:{...running,job_id:"two"},queued:[]});
resolveFinal({job_id:"one",status:"done",processing:{terminal:true}});
await finishing;
assert.equal(api.current().job_id,"two");
console.log("Queue progress follows the selected waiting job, keeps unknown percentages honest and rejects stale completion: passed");
