import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const code = fs.readFileSync(new URL("../../static/js/sharedUiStore.js", import.meta.url), "utf8").replace(/^export /gm, "");
const data = new Map();
const localStorage = { getItem:k=>data.get(k)??null, setItem:(k,v)=>data.set(k,v), key:i=>[...data.keys()][i], get length(){return data.size;} };
let online = false, server = { "stemdeck.folders": {folders:["old"]} };
const writes = [];
function boot() {
  const context = vm.createContext({localStorage,structuredClone,AbortSignal,URL,Date,Math,console:{warn(){}},window:{location:{href:"http://127.0.0.1:8000/"}},
    fetch:async(url,options)=>{
      if (!online) throw new Error("Temporary startup outage");
      if (options?.method === "POST") { const values=JSON.parse(options.body).values; writes.push(values); server={...server,...values}; }
      return {ok:true,json:async()=>({values:structuredClone(server)})};
    },
  });
  vm.runInContext(code+"\nglobalThis.api={sharedGet,sharedSet};",context);
  return context.api;
}
const wanted={folders:["album","new collection"]};
await assert.rejects(boot().sharedSet("stemdeck.folders",wanted));
assert.ok(data.get("stemdeck.pending-ui-writes.v1").includes("new collection"));
online=true;
const reopened=boot();
assert.deepEqual(await reopened.sharedGet("stemdeck.folders"),wanted,"unacknowledged local edits beat a stale server after reload");
assert.deepEqual(server["stemdeck.folders"],wanted,"reload retries the durable write");
assert.equal(data.get("stemdeck.pending-ui-writes.v1"),"{}");
const concurrent=boot();
await Promise.all([concurrent.sharedSet("stemdeck.folders",{folders:["first"]}),concurrent.sharedSet("stemdeck.folders",{folders:["latest"]})]);
assert.deepEqual(server["stemdeck.folders"],{folders:["latest"]});
assert.deepEqual(await concurrent.sharedGet("stemdeck.folders"),{folders:["latest"]});
console.log("Shared UI preferences: outage recovery, reload replay and newest-write preservation passed.");
