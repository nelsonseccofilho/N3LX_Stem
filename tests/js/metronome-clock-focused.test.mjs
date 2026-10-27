import assert from "node:assert/strict";
import {createMetronome} from "../../static/js/metronome.js";
let tick, intervals=globalThis.setInterval, clears=globalThis.clearInterval;
globalThis.setInterval=(fn)=>{tick=fn;return 1};globalThis.clearInterval=()=>{};
try {
 let at=0,origin=0,rate=1,epoch=1,ready=true,starts=[],stops=0;
 const param={setValueAtTime(){},exponentialRampToValueAtTime(){},setTargetAtTime(){}};
 const ctx={get currentTime(){return at},createGain(){return {gain:param,connect(){},disconnect(){}}},createOscillator(){return {frequency:{value:0},connect(){},start(t){starts.push(t)},stop(){stops++}}}};
 const engine={audioContext:ctx,getMasterNode(){return {}},isClockReady(){return ready},getScheduleEpoch(){return epoch},sourceTimeToCtxTime(t){return at+(t-origin)/rate},ctxTimeToSourceTime(){return origin}};
 const m=createMetronome(engine,[.1,.6,1.1,1.6,2.1]);m.setEnabled(true);assert.equal(starts[0],.1);
 at=1;origin=1;epoch++;tick();assert.ok(Math.abs(starts.at(-1)-1.1)<1e-9);
 at=2;origin=1;rate=.5;epoch++;tick();assert.ok(Math.abs(starts.at(-1)-2.2)<1e-9);
 let before=starts.length;ready=false;tick();assert.equal(starts.length,before);
 ready=true;at=3;origin=0;rate=1;epoch++;tick();assert.ok(Math.abs(starts.at(-1)-3.1)<1e-9);
 m.setBeats([.2,.7,1.2]);at=4;origin=0;epoch++;tick();assert.ok(Math.abs(starts.at(-1)-4.2)<1e-9);
 m.destroy();console.log('PASS: play, seek, rate, pause, loop and grid change re-anchor the audio clock');
} finally {globalThis.setInterval=intervals;globalThis.clearInterval=clears}
