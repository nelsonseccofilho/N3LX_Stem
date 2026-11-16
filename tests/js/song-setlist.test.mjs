import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createSetlistPlayer } from "../../static/js/setlistPlayer.js";
import * as library from "../../static/js/setlistLibrary.js";

const stored = new Map([["stemdeck:setlist", { selectedId:"p1",playlists:[
  { id:"p1",name:"Original",entries:[{id:"a",mix:{bass:{volume:.7,muted:true}}}],metro:{enabled:true,countInBars:2} },
  { id:"p2",name:"Outra",entries:[],metro:{enabled:false,countInBars:0} },
]}], ["stemdeck:mix:c", {bass:{volume:.4,muted:false}}]]);
const context = vm.createContext({ console, structuredClone, setTimeout, clearTimeout, crypto:{randomUUID:()=>"new-id"},
  ...library, createSetlistPlayer, t:key=>key, onLanguageChange(){},
  document:{addEventListener(){},getElementById:()=>null},
  storeGet:async(key,fallback)=>structuredClone(stored.get(key)??fallback),
  storeSet:async(key,value)=>stored.set(key,structuredClone(value)), flushStoreWrites:async()=>{},
  getMetronomePrefs:()=>({}), setMetronomePreferenceScope(){}, stopTransport(){}, startPreparedPlayback:async()=>true,
});
const source=fs.readFileSync(new URL("../../static/js/setlist.js",import.meta.url),"utf8").replace(/^import[^;]+;\r?\n/gm,"").replace(/^export /gm,"");
vm.runInContext(source+"\nglobalThis.api={initSetlist,addSongToSetlist,getSetlistChoices};",context);
await context.api.initSetlist({tracks:()=>["a","b","c"].map(id=>({id,title:id})),changed(){},open(){}});
const original=library.normalizeSetlists(stored.get("stemdeck:setlist"),()=>"unused").playlists[0];
assert.equal((await context.api.addSongToSetlist("c","p2")).exists,false);
assert.equal((await context.api.addSongToSetlist("c","p2")).exists,true);
assert.equal(stored.get("stemdeck:setlist").playlists[1].entries.length,1);
assert.equal(stored.get("stemdeck:setlist").playlists[1].entries[0].mix.bass.volume,.4);
assert.deepEqual(stored.get("stemdeck:setlist").playlists[0],original);
await context.api.addSongToSetlist("c",null,"Novo ensaio");
const next=stored.get("stemdeck:setlist");
assert.equal(next.selectedId,"p1"); assert.equal(next.playlists[2].name,"Novo ensaio");
assert.equal(next.playlists[2].entries[0].id,"c");
assert.deepEqual(next.playlists[0],original);
await assert.rejects(context.api.addSongToSetlist("missing","p2"));
await assert.rejects(context.api.addSongToSetlist("c",null,"  "));
await assert.rejects(context.api.addSongToSetlist("c","removed"));
console.log("Song → setlist: current mix copied, duplicates avoided, original playlist/scope preserved: passed");
