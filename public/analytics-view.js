import {mountAdmin} from './admin-analytics.js?v=20261015-view-6';

export async function mountView(frame, isCurrent) {
 let authenticated=false;
 async function request(path,options={}) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
  try {
   const response=await fetch('/api/analytics-view'+path,{method:options.method||'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal,
    headers:options.body?{'Content-Type':'application/json'}:{},body:options.body?JSON.stringify(options.body):undefined});
   const data=await response.json();
   if(!response.ok){if(response.status===401&&authenticated&&isCurrent()){authenticated=false;login()}throw new Error(data.error?.message||'Не удалось открыть аналитику. Попробуйте ещё раз.')}
   return data;
  } catch(error) {
   if(error.name==='AbortError')throw new Error('Ответ не пришёл вовремя. Попробуйте ещё раз.');
   if(error instanceof TypeError||error instanceof SyntaxError)throw new Error('Не удалось подключиться. Проверьте подключение и попробуйте ещё раз.');
   throw error;
  } finally {clearTimeout(timer)}
 }
 async function show() {
  if(!isCurrent())return;
  authenticated=true;
  await mountAdmin(frame,{readOnly:true,request:dates=>request('/report?'+new URLSearchParams(dates)),logout:async()=>{
   await request('/session',{method:'DELETE'});authenticated=false;if(isCurrent())login();
  }});
 }
 function login(enabled=true) {
  frame('<h1>Аналитика</h1>'+(enabled?'<form id="analytics-view-login" class="auth-form"><div class="field"><label for="analytics-view-password">Пароль для просмотра</label><input id="analytics-view-password" name="password" type="password" autocomplete="current-password" maxlength="128" required></div><p id="analytics-view-error" role="alert"></p><button class="button primary" type="submit">Открыть аналитику</button></form>':'<p>Доступ по ссылке отключён.</p>'),'narrow');
  const form=document.querySelector('#analytics-view-login');if(!form)return;
  form.addEventListener('submit',async e=>{
   e.preventDefault();e.stopPropagation();const button=form.querySelector('button');button.disabled=true;const error=form.querySelector('#analytics-view-error');error.textContent='';
   try {await request('/session',{method:'POST',body:{password:form.elements.password.value}});if(isCurrent()&&form.isConnected)await show()}
   catch(e){if(form.isConnected)error.textContent=e.message}
   finally{if(button.isConnected)button.disabled=false}
  });
 }
 frame('<p role="status">Открываем аналитику…</p>','narrow');
 try {const status=await request('/session');if(!isCurrent())return;if(status.authenticated)await show();else login(status.enabled)}
 catch(e){if(isCurrent()){login();document.querySelector('#analytics-view-error').textContent=e.message}}
}
