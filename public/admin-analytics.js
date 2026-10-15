import {adminRequest} from './api.js?v=20261013-analytics-6';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>v==null?'—':Number(v).toLocaleString('ru-RU',{maximumFractionDigits:2});
const date=v=>v?new Date(v*1000).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'}):'—';
const day=v=>new Date(v+'T12:00:00Z').toLocaleDateString('ru-RU',{timeZone:'Europe/Moscow',day:'numeric',month:'short'});
const rate=v=>v?.value==null?'—':number(v.value)+'%';
const money=v=>v==null?'—':Number(v).toLocaleString('ru-RU',{maximumFractionDigits:6})+' уч. ед.';
const costValue=(total,known,priced)=>total!=null?money(total):priced?'≥ '+money(known):'—';
const duration=v=>v==null?'—':`${Math.floor(Math.round(v)/60)}:${String(Math.round(v)%60).padStart(2,'0')}`;
const table=(heads,rows,numeric=[])=>rows.length?`<div class="admin-table" tabindex="0" aria-label="Таблица с горизонтальной прокруткой"><table><thead><tr>${heads.map((h,i)=>`<th scope="col"${numeric.includes(i)?' class="num"':''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((c,i)=>`<td${numeric.includes(i)?' class="num"':''}>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="admin-empty">За этот период данных нет.</p>';
const btn=(label,action,extra='')=>`<button type="button" class="button secondary" data-admin="${action}" ${extra}>${esc(label)}</button>`;
const roleName=v=>({student:'Учёба',professional:'Работа',other:'Другое'}[v]||v||'—');
let filters={},currentRoot=null,data=null,page='analytics',requestVersion=0,recordActor='',recordKind='practices';
const PAGE_SIZE=10;
const offsets={accounts:0,practices:0};
function shiftDay(value,days){const d=new Date(value+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10)}
function query(extra={}){return new URLSearchParams({...filters,...extra}).toString()}
function content(html){if(currentRoot?.isConnected)currentRoot.querySelector('#admin-content').innerHTML=html}
function stat(label,value) {
 return `<div class="admin-stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}
export async function mountAdmin(frame,options={}){
 page=options.page==='export'?'export':'analytics';adminTheme();++requestVersion;
 let css=document.querySelector('link[data-admin-css]');if(!css){css=document.createElement('link');css.rel='stylesheet';css.dataset.adminCss='true';document.head.append(css)}css.href='/admin-analytics.css?v=20261015-costs-4';
 const today=new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Moscow'});
 if(!filters.from)filters={from:shiftDay(today,-29),to:shiftDay(today,1),include_staff:'false'};
 frame(`<div id="admin-root"><header class="admin-heading"><h1>${page==='export'?'Выгрузка данных':'Аналитика'}</h1><nav class="admin-tabs" aria-label="Разделы аналитики"><a href="#/admin/analytics" ${page==='analytics'?'aria-current="page"':''}>Аналитика</a><a href="#/admin/analytics/export" ${page==='export'?'aria-current="page"':''}>Выгрузка данных</a></nav>${btn('Тема','theme')}</header><div class="admin-toolbar"><form id="admin-filters" class="admin-filters"><label>С<input aria-label="С даты" type="date" name="from" value="${esc(filters.from)}" required></label><label>по<input aria-label="По дату" type="date" name="to" value="${esc(shiftDay(filters.to,-1))}" required></label><label class="check"><input type="checkbox" name="include_staff" ${filters.include_staff==='true'?'checked':''}>Команда и тестовые</label><button type="submit" class="button primary">Применить</button></form><p id="admin-status" class="admin-status" role="status"></p></div><div id="admin-content"></div></div>`,'admin');
 currentRoot=document.querySelector('#admin-root');const root=currentRoot;
 root.addEventListener('submit',e=>{if(e.target.id!=='admin-filters')return;e.preventDefault();e.stopPropagation();const values=Object.fromEntries(new FormData(e.target));filters={from:values.from,to:shiftDay(values.to,1),include_staff:values.include_staff?'true':'false'};offsets.accounts=offsets.practices=0;recordActor='';void load()});
 root.addEventListener('click',e=>{const b=e.target.closest('[data-admin]');if(b){e.preventDefault();e.stopPropagation();void action(b)}});
 await load();
}
async function load(){
 const root=currentRoot,version=++requestVersion;
 content('<div class="skeleton" role="status">Загружаем данные…</div>');
 try{const result=await adminRequest('/admin/analytics/report?'+query(),{timeout:25000});if(version!==requestVersion||root!==currentRoot||!root.isConnected)return;data=result;
 const status=root.querySelector('#admin-status');status.textContent='Обновлено '+new Date(data.as_of*1000).toLocaleTimeString('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'})+' · МСК';status.title=date(data.as_of);
 if(page==='export')renderExport();else renderAnalytics();
 }catch(e){if(version===requestVersion&&root===currentRoot)content(`<div class="admin-error" role="alert">${esc(e.message)}<div class="admin-actions">${btn('Повторить','reload')}</div></div>`)}
}
function chart(rows) {
 const width=800,height=286,left=38,right=14,top=14,bottom=30;
 const peak=Math.max(1,...rows.map(d=>Math.max(d.active,d.registered)));
 const tickStep=Math.max(1,Math.ceil(peak/4)),max=Math.ceil(peak/tickStep)*tickStep;
 const plotH=height-top-bottom,plotW=width-left-right;
 const x=i=>left+(rows.length===1?plotW/2:i*plotW/(rows.length-1)),y=v=>top+plotH-v/max*plotH;
 const ticks=Array.from({length:max/tickStep+1},(_,i)=>i*tickStep);
 const labelCount=Math.min(5,rows.length),labels=new Set(Array.from({length:labelCount},(_,i)=>labelCount===1?0:Math.round(i*(rows.length-1)/(labelCount-1))));
 return `<div class="admin-chart" role="img" aria-label="Пользователи по дням: активные и новые регистрации"><svg viewBox="0 0 ${width} ${height}">${ticks.map(v=>`<line x1="${left}" y1="${y(v)}" x2="${width-right}" y2="${y(v)}" class="chart-grid"/><text x="${left-10}" y="${y(v)+4}" text-anchor="end">${number(v)}</text>`).join('')}${rows.map((r,i)=>labels.has(i)?`<line x1="${x(i)}" y1="${top}" x2="${x(i)}" y2="${height-bottom}" class="chart-grid vertical"/>`:'').join('')}${['active','registered'].map(key=>`<polyline class="chart-line ${key}" points="${rows.map((r,i)=>x(i)+','+y(r[key])).join(' ')}"/>${rows.map((r,i)=>`<circle class="chart-point ${key}" cx="${x(i)}" cy="${y(r[key])}" r="2.5"><title>${esc(day(r.day))}: ${key==='active'?'активных':'регистраций'} ${r[key]}</title></circle>`).join('')}`).join('')}${rows.map((r,i)=>labels.has(i)?`<text class="chart-date" x="${x(i)}" y="${height-6}" text-anchor="${i===0?'start':i===rows.length-1?'end':'middle'}">${esc(day(r.day))}</text>`:'').join('')}</svg></div>`;
}
function funnelRows(rows){return rows.map((r,i)=>`<li><span>${esc(r.label)}</span><strong>${number(r.count)}</strong><small>${i?rate(r.conversion):'—'}</small></li>`).join('')}
function recordsTabs() {
 return `<div class="admin-records-heading"><h2 class="sr-only">Подробные данные</h2><div class="admin-record-switch" role="group" aria-label="Показать таблицу"><button type="button" data-admin="records-tab" data-kind="practices" aria-pressed="${recordKind==='practices'}">Тренировки <span>${number(data.summary.practices)}</span></button><button type="button" data-admin="records-tab" data-kind="accounts" aria-pressed="${recordKind==='accounts'}">Аккаунты <span>${number(data.overview.accounts)}</span></button></div><span class="admin-records-period">${recordKind==='accounts'?'Регистрации к концу периода':'За выбранный период'}</span></div>`;
}
function renderAnalytics() {
 const o=data.overview,c=o.economy;
 content(`<section class="admin-overview" aria-label="Основные показатели"><div class="admin-summary">${stat('Пользователи · всего',number(o.accounts))}${stat('Начато тренировок',number(o.started_practices))}${stat('Тренировок / пользователь',number(o.average_per_user))}${stat('Тренировок / тренирующийся',number(o.average_per_trainee))}${stat('DAU · '+day(o.dau_day),number(o.dau))}${stat('За последний час',number(o.last_hour))}${stat('Retention · 7 дней',rate(o.retention_7d))}${stat('Отток · 7 дней',rate(o.churn_7d))}</div></section><section class="admin-economy" aria-label="Расходы на LLM"><h2>Расходы LLM</h2><div class="admin-costs">${stat('На тренировку',costValue(c.per_practice,c.known_per_practice,c.priced_attempts))}${stat('На пользователя',costValue(c.per_user,c.known_per_user,c.priced_attempts))}${stat('Всего',costValue(c.total,c.known_total,c.priced_attempts))}</div><span class="admin-cost-coverage">С ценой · ${c.priced_attempts}/${c.attempts} вызовов</span></section><div class="admin-two-columns"><section class="admin-block admin-users-chart"><header class="admin-block-heading"><h2>Пользователи по дням</h2><p class="admin-legend"><span>Активные</span><span>Регистрации</span></p></header>${chart(o.daily)}<details class="admin-daily-table"><summary>Таблица по дням</summary>${table(['Дата','Активные пользователи','Новые регистрации'],o.daily.map(d=>[esc(day(d.day)),number(d.active),number(d.registered)]),[1,2])}</details></section><section class="admin-block admin-conversion"><header class="admin-block-heading"><h2>Воронка</h2></header><div class="admin-funnel-heading"><span>Визиты с лендинга</span><span>Число</span><span>Конверсия</span></div><ol class="admin-funnel">${funnelRows(o.acquisition_funnel)}</ol><div class="admin-funnel-heading"><span>Тренировки</span><span>Число</span><span>Конверсия</span></div><ol class="admin-funnel">${funnelRows(o.training_funnel)}</ol></section></div><section class="admin-records" aria-label="Аккаунты и тренировки">${recordsTabs()}<div id="accounts-records" ${recordKind==='accounts'?'':'hidden'}></div><div id="practices-records" ${recordKind==='practices'?'':'hidden'}></div></section><div id="practice-detail"></div>`);
 void loadRecords(recordKind);
}
function renderExport(){
 content(`<section class="admin-export"><h2>Данные за выбранный период</h2>${table(['Данные','CSV для Excel','JSON'],[['summary','Основные показатели'],['daily','Пользователи по дням'],['accounts','Аккаунты и регистрационные данные'],['practices','Тренировки, длительность и расходы'],['funnel','Этапы воронки и конверсия']].map(([key,label])=>[esc(label),`<a download href="/api/admin/analytics/export?${esc(query({dataset:key,format:'csv'}))}">Скачать CSV</a>`,`<a download href="/api/admin/analytics/export?${esc(query({dataset:key,format:'json'}))}">Скачать JSON</a>`]))}<a class="button primary" download href="/api/admin/analytics/export?${esc(query({dataset:'all',format:'zip'}))}">Скачать всё в ZIP</a></section>`);
}
async function selectRecords(kind) {
 recordKind=kind;
 for(const button of currentRoot.querySelectorAll('[data-admin="records-tab"]'))button.setAttribute('aria-pressed',String(button.dataset.kind===kind));
 for(const name of ['accounts','practices'])currentRoot.querySelector('#'+name+'-records').hidden=name!==kind;
 currentRoot.querySelector('.admin-records-period').textContent=kind==='accounts'?'Регистрации к концу периода':'За выбранный период';
 await loadRecords(kind);
}
async function loadRecords(kind){
 const root=currentRoot,version=requestVersion,target=root.querySelector('#'+kind+'-records');if(!target)return;
 target.innerHTML='<p role="status">Загружаем…</p>';
 try{const r=await adminRequest('/admin/analytics/'+kind+'?'+query({kind:'all',offset:offsets[kind],limit:PAGE_SIZE,...(kind==='practices'&&recordActor?{actor_id:recordActor}:{})}));if(root!==currentRoot||version!==requestVersion||!target.isConnected)return;
 const rows=kind==='accounts'?r.items.map(u=>[esc(u.full_name),esc(u.email),date(u.created),esc(roleName(u.role)),number(u.practices||0),`<details><summary>Данные аккаунта</summary><dl><dt>Полное имя</dt><dd>${esc(u.full_name)}</dd><dt>Фамилия, имя, отчество отдельно</dt><dd>Не запрашивались при регистрации</dd><dt>IP-адрес</dt><dd>Не сохранялся</dd><dt>Первое знакомство</dt><dd>${u.onboarding_completed?'Завершено':'Не завершено'}</dd></dl>${btn('Тренировки пользователя','account-practices',`data-id="${u.id}"`)}</details>`]):r.items.map(p=>[`<button class="text-button" data-admin="detail" data-id="${p.id}">${esc(p.participant)}</button>`,date(p.created),duration(p.seconds),costValue(p.cost.total,p.cost.known_cost,p.cost.priced_attempts),`<span class="admin-state ${p.failures&&!p.complete?'failed':''}">${p.complete?'Завершена':p.failures?'Ошибка обработки':p.speech_at?'В процессе':'Не начата'}</span>`,p.rating==null?'—':number(p.rating)+'/5',`${p.answers}${p.questions?'/3':' · без вопросов'}`]);
 target.innerHTML=(kind==='practices'&&recordActor?`<p class="admin-record-filter">Тренировки выбранного пользователя · ${btn('Все пользователи','reset-account')}</p>`:'')+table(kind==='accounts'?['Имя при регистрации','Email','Регистрация · Москва','Цель','Тренировки','Подробности']:['Участник','Создана · Москва','Записано, мин:с','Расходы LLM','Результат','Оценка отчёта','Ответы'],rows,kind==='accounts'?[4]:[2,3,5,6])+`<div class="admin-pagination"><span>${r.total?offsets[kind]+1:0}–${Math.min(offsets[kind]+PAGE_SIZE,r.total)} из ${r.total}</span><div>${offsets[kind]?btn('Назад','paginate',`data-kind="${kind}" data-direction="-1"`):''}${offsets[kind]+PAGE_SIZE<r.total?btn('Далее','paginate',`data-kind="${kind}" data-direction="1"`):''}</div></div>`;
 }catch(e){if(target.isConnected)target.innerHTML=`<p class="admin-error" role="alert">${esc(e.message)}</p>${btn('Повторить','records',`data-kind="${kind}"`)}`}
}
async function action(b){
 b.disabled=true;try{
 const a=b.dataset.admin;
 if(a==='theme'){const dark=document.body.dataset.adminTheme!=='dark';document.body.dataset.adminTheme=dark?'dark':'light';try{localStorage.setItem('nfs-admin-theme',dark?'dark':'light')}catch{}}
 else if(a==='reload')await load();
 else if(a==='paginate'){offsets[b.dataset.kind]=Math.max(0,offsets[b.dataset.kind]+PAGE_SIZE*Number(b.dataset.direction));await loadRecords(b.dataset.kind)}
 else if(a==='records')await loadRecords(b.dataset.kind);
 else if(a==='records-tab'){await selectRecords(b.dataset.kind)}
 else if(a==='detail')await detail(b.dataset.id);
 else if(a==='account-practices'){recordActor=b.dataset.id;offsets.practices=0;await selectRecords('practices');currentRoot.querySelector('.admin-records').scrollIntoView({block:'start',behavior:'instant'})}
 else if(a==='reset-account'){recordActor='';offsets.practices=0;await loadRecords('practices')}
 else if(a==='classify'){await adminRequest('/admin/analytics/account-classifications/'+b.dataset.id,{method:'PATCH',body:{classification:b.dataset.classification}});await load()}
 }catch(e){if(currentRoot?.isConnected)currentRoot.querySelector('#practice-detail')?.insertAdjacentHTML('afterbegin',`<p class="admin-error" role="alert">${esc(e.message)}</p>`)}finally{if(b.isConnected)b.disabled=false}
}

const eventNames={provider_cost_recorded:'Расходы на обработку сохранены',admin_evidence_opened:'Открыты данные тренировки',admin_data_export:'Данные выгружены',registration_confirmed:'Аккаунт создан',practice_created:'Тренировка создана',segment_saved:'Запись сохранена',segment_capture_bound:'Запись связана с попыткой',job_requested:'Обработка запрошена',job_transition:'Состояние обработки изменилось',questions_generated:'Вопросы готовы',report_generated:'Разбор готов',capture_started:'Запись началась',capture_stopped:'Запись остановлена',capture_interrupted:'Запись прервалась',question_presented:'Вопрос показан',answer_started:'Ответ начался',answer_recorded:'Ответ записан',report_viewed:'Разбор показан',report_engaged:'Разбор открыт ≥10 секунд',feedback_submitted:'Оценка сохранена',page_viewed:'Страница показана',registration_viewed:'Регистрация открыта',registration_submitted:'Регистрация отправлена',login:'Вход в аккаунт',logout:'Выход из аккаунта',service_failure:'Ошибка сервиса',request:'Запрос',provider_attempt_started:'Обращение к AI началось',provider_attempt_finished:'Обращение к AI завершилось',practice_resumed:'Возврат к тренировке'};
function trace(result){if(!result.items.length)return '<p class="admin-empty">Событий по выбранным условиям нет.</p>';return `<ol class="admin-events">${result.items.map(e=>`<li><strong>${esc(eventNames[e.kind]||e.kind)}</strong><div class="meta">${date(e.occurred)}${e.level==='ERROR'?' · Ошибка':''}${e.delayed?' · С задержкой':''} · ${e.origin==='reconstructed'?'История до включения журнала':e.origin==='server_confirmed'?'Действие сервиса':'Действие на странице'}</div><details><summary>Подробности</summary><pre>${esc(JSON.stringify({event_id:e.event_id,practice_id:e.practice_id,request_id:e.request_id,correlation_id:e.correlation_id,received_at:date(e.received),release:e.release,data:e.data},null,2))}</pre></details></li>`).join('')}</ol>`}
async function detail(id){
 const p=await adminRequest('/admin/analytics/practices/'+id);const el=currentRoot.querySelector('#practice-detail');if(!el)return;
 el.innerHTML=`<section class="admin-panel"><h2>${esc(p.config.topic||'Тренировка')}</h2><dl><dt>Участник</dt><dd>${esc(p.participant.name)} · ${esc(p.participant.email)}</dd><dt>Время</dt><dd>${esc(p.config.duration)} мин.</dd></dl><h3>Записи и ответы</h3>${p.segments.map(s=>`<article><h4>${s.kind==='speech'?'Выступление':`Ответ ${s.index}`}</h4><p class="meta">Сохранено: ${date(s.saved_at)} · ${number(s.duration_seconds)} с</p>${s.kind==='answer'?`<p>${esc(p.questions[s.index-1]||'')}</p>`:''}${s.available?`<details><summary>Контрольные суммы</summary><p>Сохранённый файл: <code>${esc(s.stored_sha256)}</code></p><p>Исходная загрузка: <code>${esc(s.upload_sha256||'Не сохранена')}</code></p></details><${s.has_video?'video':'audio'} controls preload="metadata" src="${esc(s.media_url)}"></${s.has_video?'video':'audio'}><a href="${esc(s.media_url)}?download=true">Скачать запись</a>`:'<p>Файл недоступен.</p>'}<details><summary>Расшифровка</summary><p>${esc(s.transcript||'Расшифровка ещё не готова.')}</p></details></article>`).join('')}<h3>Версии разбора</h3>${p.versions.map(v=>`<details><summary>${date(v.finished)}</summary>${['strengths','recommendations','criteria'].map(k=>`<h4>${({strengths:'Что получается',recommendations:'Что попробовать',criteria:'Выбранные критерии'})[k]}</h4>${(v.report[k]||[]).map(x=>`<article><strong>${esc(x.title||x.criterion||'')}</strong><p>${esc(x.observation||x.reason||x.text||'')}</p><p>${esc(x.action||'')}</p>${x.example?`<p><strong>Возможная формулировка</strong> ${esc(x.example)}</p>`:''}${x.evidence?`<blockquote>${esc(x.evidence)}</blockquote>`:''}</article>`).join('')}`).join('')}${v.report.insight?`<p>${esc(v.report.insight)}</p>`:''}${v.report.metrics?.length?table(['Показатель','Значение'],v.report.metrics.map(m=>[esc(m.title||m.label),esc(m.text??m.value??'')])):''}${v.report.limitations?.length?`<p>${v.report.limitations.map(esc).join(' ')}</p>`:''}<details><summary>Полный сохранённый результат</summary><pre>${esc(JSON.stringify(v.report,null,2))}</pre></details></details>`).join('')||'<p>Готового разбора нет.</p>'}<h3>Отзывы</h3>${p.feedback.map(f=>`<p>${f.rating}/5 · ${date(f.created)}<br>${esc(f.text)}</p>`).join('')||'<p>Отзыва пока нет.</p>'}<details><summary>История тренировки</summary>${trace(p.trace)}</details><details><summary>Категория аккаунта</summary><div class="admin-actions">${['participant','staff','test','unknown'].map(c=>btn(({participant:'Участник',staff:'Команда',test:'Тестовый',unknown:'Не определено'})[c],'classify',`data-id="${p.participant.id}" data-classification="${c}"`)).join('')}</div></details></section>`;el.scrollIntoView({block:'start',behavior:'instant'});
}
function adminTheme(){let dark=false;try{dark=localStorage.getItem('nfs-admin-theme')==='dark'}catch{}document.body.dataset.adminTheme=dark?'dark':'light'}
