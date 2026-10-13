// Safe UI observations only. Server milestones cannot be submitted here.
let queue=[],busy=false,actor=null,enabled=true,touchSent=false;
const key='nfs-safe-analytics-v1';
const uid=()=>crypto.randomUUID().replaceAll('-','');
try{queue=JSON.parse(sessionStorage.getItem(key)||'[]').filter(e=>e.occurred>Date.now()/1000-86400).slice(-500)}catch{}
function persist(){try{while(JSON.stringify(queue).length>262144&&queue.length)queue.shift();sessionStorage.setItem(key,JSON.stringify(queue))}catch{}}
export function analyticsActor(id){const previous=actor;actor=id||null;if(previous&&previous!==actor){queue=[];touchSent=false}queue=queue.filter(e=>!e.actor_context||e.actor_context===actor);persist()}
export function track(kind,data={},practiceId=null){
  if(!enabled||location.hash.startsWith('#/admin'))return;
  queue.push({id:uid(),schema_version:1,kind,data,practice_id:practiceId==='guest'?null:practiceId,actor_context:actor,occurred:Date.now()/1000});
  if(queue.length>500)queue.splice(0,queue.length-500);persist();
  if(['page_viewed','registration_viewed','report_viewed'].includes(kind))void flush();
}
function touch(){
  const p=new URLSearchParams(location.search);let host='';try{host=new URL(document.referrer).hostname}catch{}
  const engines={'google.com':'google','www.google.com':'google','google.ru':'google','www.google.ru':'google','yandex.ru':'yandex','www.yandex.ru':'yandex','yandex.com':'yandex','ya.ru':'yandex','bing.com':'bing','www.bing.com':'bing'};
  const source=p.get('utm_source')||(host&&host!==location.hostname?(engines[host]||host):'direct');
  return {source,medium:p.get('utm_medium')||(p.get('utm_source')?'unknown':source==='direct'?'none':engines[host]?'organic':'referral'),campaign:p.get('utm_campaign')||'',campaign_id:p.get('utm_id')||p.get('utm_campaign')||'',content:p.get('utm_content')||'',term:p.get('utm_term')||'',referrer_host:host};
}
export async function flush(){
  if(busy||!enabled||!queue.length)return;busy=true;
  const batch=queue.slice(0,50);
  try{
    const r=await fetch('/api/analytics/events',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({events:batch,...(!touchSent?{touch:touch()}: {})}),signal:AbortSignal.timeout(8000),keepalive:true});
    if(r.ok){const a=await r.json();if(a.disabled){enabled=false;queue=[];persist();return}const done=new Set([...a.accepted,...a.duplicates,...a.rejected]);queue=queue.filter(e=>!done.has(e.id));touchSent=true;persist()}
  }catch{}finally{busy=false}
}
setInterval(()=>void flush(),5000);
addEventListener('pagehide',()=>{if(queue.length)navigator.sendBeacon?.('/api/analytics/events',new Blob([JSON.stringify({events:queue.slice(0,50)})],{type:'application/json'}))});
document.addEventListener('click',e=>{
  const target=e.target.closest('a,button');if(!target)return;
  if(document.body.dataset.view==='landing'&&target.matches('a.button'))track('landing_cta_clicked',{cta_id:target.closest('section')?.className.split(' ')[0]||'landing'});
});
export function trackPage(path,p){
  if(path.startsWith('/admin'))return;
  track('page_viewed',{route_id:path.replace(/\/practice\/.*/, '/practice'),page_view_id:uid()});
  if(path==='/register')track('registration_viewed',{});
  if(path==='/app')track('setup_viewed',{});
  if(p&&path.startsWith('/practice'))track('practice_resumed',{},p.id);
}
export function observeReport(p){
  const version=p.report_version_id||(p.latest_job?.kind==='report'&&p.latest_job.status==='succeeded'?p.latest_job.id:null);
  if(!version)return;
  const page=uid();let observed=false,elapsed=0;
  function visible(){if(document.hidden||!document.querySelector('.report-reading')||location.hash!==`#/practice/${p.id}`)return false;return true}
  const timer=setInterval(()=>{
    if(!document.querySelector('.report-reading')||location.hash!==`#/practice/${p.id}`){clearInterval(timer);return}
    if(!visible())return;
    if(!observed){track('report_viewed',{report_version_id:version,page_view_id:page},p.id);observed=true}
    elapsed++;if(elapsed>=10){track('report_engaged',{report_version_id:version,page_view_id:page,visible_seconds:10},p.id);clearInterval(timer)}
  },1000);
}
