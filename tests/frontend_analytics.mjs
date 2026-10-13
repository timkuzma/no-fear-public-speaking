import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
const intervals=new Map(), storage=new Map(), delivered=[];let counter=0;
const document={hidden:false,querySelector:()=>({}),addEventListener(){}};
const scope=vm.createContext({crypto:{randomUUID},document,location:{hash:'#/practice/'+'a'.repeat(32),search:'',hostname:'fixture'},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},URLSearchParams,URL,Date,Set,JSON,Blob,AbortSignal,
 setInterval:fn=>{const id=++counter;intervals.set(id,fn);return id},clearInterval:id=>intervals.delete(id),addEventListener(){},navigator:{},fetch:async(_url,options)=>{const body=JSON.parse(options.body);delivered.push(body);return{ok:true,json:async()=>({accepted:body.events.map(e=>e.id),duplicates:[],rejected:[]})}}});
vm.runInContext(readFileSync(new URL('../public/analytics.js',import.meta.url),'utf8').replaceAll('export ', '')+'\nglobalThis.ui={track,observeReport,flush,analyticsActor};',scope);
scope.ui.analyticsActor('b'.repeat(32));scope.ui.observeReport({id:'a'.repeat(32),report_version_id:'c'.repeat(32)});
const observer=intervals.get(2);document.hidden=true;observer();await scope.ui.flush();assert.equal(delivered.length,0,'A hidden report is not a view');
document.hidden=false;observer();await new Promise(setImmediate);await scope.ui.flush();assert.equal(delivered.flatMap(x=>x.events).filter(e=>e.kind==='report_viewed').length,1);
for(let i=0;i<9;i++)observer();await new Promise(setImmediate);await scope.ui.flush();assert.equal(delivered.flatMap(x=>x.events).filter(e=>e.kind==='report_engaged').length,1);
assert.equal(delivered.flatMap(x=>x.events).find(e=>e.kind==='report_viewed').data.report_version_id,'c'.repeat(32));
scope.ui.track('capture_started',{capture_id:'d'.repeat(32)},'a'.repeat(32));scope.ui.analyticsActor('e'.repeat(32));await scope.ui.flush();assert.equal(delivered.flatMap(x=>x.events).filter(e=>e.kind==='capture_started').length,0,'Queued observations must not cross owners');
console.log('Frontend analytics: visibility, version binding, engagement and owner rotation passed');
