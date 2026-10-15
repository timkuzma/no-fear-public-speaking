import { track, trackPage, analyticsActor, observeReport, flush } from "./analytics.js?v=20261013-analytics-6";
import { installTypography } from "./typography.js?v=20261013-type";
import { mountLandingMotion, animateContextChange } from "./landing-motion.js?v=20261013-stable-scroll";
import { api } from "./api.js?v=20261013-analytics-6";
import { LiveAudioCapture } from "./live-audio.js?v=20261013-asr-5s";
import {
  saveDraft,
  loadDraft,
  clearDraft,
  saveRecordingDraft,
  loadRecordingDrafts,
  clearRecordingDraft,
} from "./guest-draft.js?v=20261013-practice-settings";
const app = document.querySelector("#app");
const CURRENT_REPORT_VERSION = "speech-feedback-v2.4";
let landingCleanup = () => {};
const state = {
  user: null,
  adminReturn: false,
  providerReady: false,
  online: true,
  practice: null,
  guest: null,
  guestPersisted: false,
  guestNotice: "",
  recorder: null,
  stream: null,
  cameraStream: null,
  cameraBusy: false,
  cameraVersion: 0,
  audioContext: null,
  liveCapture: null,
  recording: false,
  recordingWithVideo: false,
  pending: null,
  pendingPersisted: false,
  draftWrites: Promise.resolve(),
  recordingOwnerId: null,
  authReturn: null,
  recordingError: "",
  timer: null,
  raf: null,
  poll: null,
  routeVersion: 0,
  uploading: false,
  meetingPracticeId: null,
  answerQueue: [],
  answerPump: null,
  seenQuestionChats: new Set(),
  questionsJustReady: null,
};
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const heading = (value) =>
  escape(
    String(value ?? "")
      .trim()
      .replace(/[.\u2026]+$/u, ""),
  );
const date = (value) => {
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("ru-RU", {
        day: "numeric",
        month: "long",
        hour: "2-digit",
        minute: "2-digit",
      });
};
const time = (seconds) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const route = () => location.hash.slice(1) || "/landing";
const go = (path) => {
  if (route() === path) void navigate();
  else location.hash = path;
};
function notify(text) {
  const el = document.querySelector("#toast");
  el.textContent = text;
  el.classList.add("visible");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => el.classList.remove("visible"), 4500);
}
function errorText(error) {
  const messages = {
    STORAGE_CAPACITY: "Не получилось сохранить запись. Не закрывай страницу и повтори сохранение позже.",
    MAINTENANCE: "Тренировка временно недоступна. Не закрывай страницу, если запись ещё не сохранена, и попробуй позже.",
    UPLOAD_KEY_CONFLICT: "На этом этапе уже есть другая запись. Твоя запись не потерялась.",
    SEGMENT_EXISTS: "На этом этапе уже есть сохранённая запись.",
    PRACTICE_LOCKED: "Эта тренировка уже завершена или для неё готовится разбор.",
    PRACTICE_BUSY: "Сначала дождись готового разбора, затем можно удалить тренировку.",
    STORAGE_NOT_READY: "Не получилось сохранить запись. Не закрывай страницу и попробуй ещё раз.",
    AI_NOT_CONFIGURED: "Разбор пока недоступен. Запись сохранена; попробуй позже.",
    MEDIA_NOT_CONFIGURED: "Запись пока недоступна. Попробуй позже.",
    AI_QUEUE_FULL: "Сейчас готовится много разборов. Запись сохранена; попробуй чуть позже.",
    AI_USER_LIMIT: "На сегодня доступные разборы закончились. Запись сохранена; продолжи завтра.",
    AI_SERVICE_LIMIT: "Разбор временно недоступен. Запись сохранена; попробуй позже.",
    AI_QUOTA: "На сегодня доступные разборы закончились. Запись сохранена; продолжи завтра.",
    AI_RATE_LIMIT: "Разбор пока занят. Запись сохранена; попробуй чуть позже.",
    AI_INVALID_RESPONSE: "Не получилось подготовить вопросы или разбор. Запись сохранена; попробуй ещё раз.",
    MEDIA_INVALID: "Не удалось прослушать запись. Проверь микрофон и запиши речь ещё раз.",
    REQUEST_INVALID: "Проверь заполненные поля и попробуй ещё раз.",
  };
  if (messages[error?.code]) return messages[error.code];
  const message = error?.message || "";
  if (!/[а-яё]/iu.test(message) || /сервер|браузер|расшифров|обработк|идентификатор|сесси|черновик|\b(?:API|ASR|JSON|LLM|HTTP|SQL|Blob)\b/iu.test(message))
    return "Не удалось выполнить действие. Попробуй ещё раз.";
  return message;
}
function errorBox(text) {
  return `<div class="notice error" role="alert">${escape(text)}</div>`;
}
function button(text, action, cls = "primary", extra = "") {
  return `<button class="button ${cls}" type="button" data-action="${action}" ${extra}>${text}</button>`;
}
function startLink(text = "Начать тренировку", cls = "primary") {
  return `<a class="button ${cls}" href="#${state.user ? "/app" : "/register"}">${text}</a>`;
}
function telemetry(kind,data={},practiceId=null){try{if(typeof track==="function")track(kind,data,practiceId)}catch{}}
function header() {
  return `<header class="header"><a class="home-link" href="#/landing">Главная</a><nav class="primary-nav" aria-label="Основная навигация">${state.user ? `<a href="#/app">Тренировка</a><a href="#/history">История</a>${state.user.analytics_access ? '<a href="#/admin/analytics">Аналитика</a>' : ""}` : `<a href="#/login">Вход</a><a class="registration-link" href="#/register">Регистрация</a>`}</nav>${state.user ? `<div class="account-actions">${button("Выход", "logout", "text")}</div>` : ""}</header>`;
}
function frame(content, kind = "workspace") {
  landingCleanup();
  landingCleanup = () => {};
  document.body.dataset.view = kind;
  app.innerHTML = `${kind === "meeting" ? "" : header()}<main id="main" class="${kind}" tabindex="-1">${content}</main>${kind === "meeting" ? "" : '<footer><span>Сцена без страха</span></footer>'}`;
  queueMicrotask(() =>
    document.querySelector("#main")?.focus({ preventScroll: true }),
  );
  document.title =
    kind === "landing"
      ? "Сцена без страха · Репетиция выступлений"
      : "Тренировки · Сцена без страха";
}
function landing() {
  frame(
    `<section class="landing-hero" aria-labelledby="landing-title">
      <div class="landing-hero-copy">
        <p class="landing-kicker">Сцена без страха · Репетиция выступлений</p>
        <h1 id="landing-title">Отрепетируй речь до встречи с аудиторией</h1>
        <p class="landing-lead">Запиши выступление, ответь на вопросы по сказанному и выбери, что улучшить в следующей попытке.</p>
        ${state.user ? "" : `<p class="landing-start-note">Зарегистрируйся или войди, чтобы записать выступление и получить разбор.</p>`}
        <div class="landing-hero-actions">${startLink("Начать тренировку", "primary landing-cta")}</div>
      </div>
    </section>
    <section class="landing-contexts landing-light" id="landing-contexts" aria-labelledby="contexts-title">
      <div class="landing-section-heading"><p class="landing-kicker">Под твою задачу</p><h2 id="contexts-title">Когда важно объяснить свою мысль</h2><p>Выбери ситуацию и посмотри, на чём можно сосредоточиться в тренировке.</p></div>
      <div class="landing-context-grid" role="group" aria-label="Ситуация для тренировки">
        ${[
          ["speech", "Выступление", "Главная мысль и понятные аргументы"],
          ["defense", "Защита проекта", "Идея, решение и вопросы к ним"],
          ["free", "Свободная речь", "Тема, которую хочется обсудить"],
        ].map(([key, title, copy], index) => `<button class="landing-context-card" type="button" data-action="landing-context" data-context="${key}" aria-pressed="${index === 0}" aria-controls="landing-context-panel"><span class="landing-context-mark" aria-hidden="true">${landingContextIcon(key)}</span><strong>${title}</strong><span>${copy}</span><span class="context-selected" aria-hidden="true">Выбрано</span></button>`).join("")}
      </div>
      <div class="landing-context-panel" id="landing-context-panel"><div class="landing-context-copy" id="landing-context-copy" aria-live="polite">${["speech", "defense", "free"].map((key) => `<div data-context-copy="${key}" aria-hidden="${key !== "speech"}">${landingContextCopy(key)}</div>`).join("")}</div>${startLink("Начать тренировку", "secondary")}</div>
    </section>
    <section class="landing-meeting landing-light" aria-labelledby="meeting-title">
      <figure class="landing-meeting-visual"><div class="landing-meeting-frame"><div class="landing-meeting-caption"><span>Пространство для репетиции</span><span>Твоё выступление</span></div><img src="/audience-meeting-v1.png" width="1536" height="1024" alt="Иллюстрация виртуальной аудитории в переговорной" loading="lazy"><div class="landing-meeting-tools" aria-hidden="true">${deviceIcon("mic")}${deviceIcon("camera")}</div></div></figure>
      <div class="landing-feature-copy"><p class="landing-kicker">Знакомая обстановка</p><h2 id="meeting-title">Говори так, как будешь говорить на встрече</h2><p>Микрофон, камера по желанию и слушатели перед тобой. После выступления вопросы появляются в чате этой же встречи.</p><ul class="landing-feature-list"><li><strong>Запись сохраняется</strong><span>После завершения выступления можно вернуться к своей попытке.</span></li><li><strong>Вопросы по твоим словам</strong><span>Вопросы относятся к тому, что ты рассказал.</span></li><li><strong>Один фокус для повторения</strong><span>В разборе выбираешь рекомендацию для следующей тренировки.</span></li></ul></div>
    </section>
    <section class="landing-method" aria-labelledby="method-title">
      <div class="landing-section-heading"><p class="landing-kicker">Путь тренировки</p><h2 id="method-title">От выступления к разбору и новой попытке</h2></div>
      <ol class="landing-process">
        <li><span class="landing-step">1</span><h3>Запиши выступление</h3><p>Выбери тему и время выступления, затем запиши свою речь. Можно закончить раньше.</p></li>
        <li><span class="landing-step">2</span><h3>Ответь на вопросы</h3><p>Три вопроса по содержанию появятся в чате. Запиши ответы и получи разбор речи с цитатами.</p></li>
        <li><span class="landing-step">3</span><h3>Попробуй ещё раз</h3><p>Выбери одну рекомендацию. Тема и фокус перейдут в новую тренировку.</p></li>
      </ol>
      <div class="landing-method-action">${startLink("Начать тренировку", "primary landing-cta")}</div>
    </section>
    <section class="landing-faq landing-light" aria-labelledby="faq-title">
      <div class="landing-faq-heading"><p class="landing-kicker">Перед важным выступлением</p><h2 id="faq-title">Как репетиция поможет тебе подготовиться</h2><p>О том, что попробовать до выступления и как использовать обратную связь.</p></div>
      <div class="landing-faq-list">
        <details><summary>До выступления мало времени. С чего начать?</summary><div><p>Начни с короткой репетиции любого фрагмента своего выступления. После вопросов и разбора выбери одну рекомендацию для следующей попытки — например, уточнить вывод. Так у тебя будет понятная задача для оставшегося времени вместо попытки переделать всё выступление сразу.</p></div></details>
        <details><summary>Я знаю тему, но говорю сумбурно. Как это исправить?</summary><div><p>Запиши объяснение своими словами. При желании укажи, на что обратить внимание в разборе. Разбор даст замечания по содержанию и рекомендации с фрагментами твоей речи. Их можно использовать, чтобы перестроить объяснение, добавить недостающий пример и попробовать рассказать ещё раз.</p></div></details>
        <details><summary>Боюсь растеряться на вопросах. Как их отрепетировать?</summary><div><p>После выступления появятся три вопроса по тому, что ты рассказал. Ты сможешь проговорить ответы и получить разбор вместе с основной речью. Это возможность заранее потренироваться объяснять свою мысль и подкреплять её аргументами. Вопросы реальной аудитории могут отличаться.</p></div></details>
        <details><summary>Что я пойму о своей речи после первой попытки?</summary><div><p>Увидишь, что в объяснении уже получается и что стоит изменить в следующей попытке. Например, рекомендация может касаться общего аргумента, которому не хватает примера. Замечания сопровождаются фрагментами твоей речи, поэтому их можно сопоставить с записью и решить, что именно доработать.</p></div></details>
        <details><summary>Чем это полезнее репетиции перед зеркалом?</summary><div><p>Перед зеркалом можно проговорить текст и посмотреть на себя. Здесь ты ещё получишь вопросы по своей речи и рекомендации по её содержанию. Это дополнительная обратная связь для проверки объяснения, когда ты уже привык к собственному тексту и не знаешь, что в нём изменить.</p></div></details>
        <details><summary>Я стесняюсь выступать. Здесь меня кто-то слушает?</summary><div><p>К тренировке не подключаются живые слушатели: перед тобой виртуальная аудитория. Вопросы и разбор создаются автоматически. Можно начать только с микрофоном и включить камеру по желанию. Ты можешь пробовать разные формулировки до того, как произнесёшь их на защите или встрече.</p></div></details>
        <details><summary>Как понять, что следующая попытка стала лучше?</summary><div><p>Выбери одну рекомендацию и проверь конкретное изменение. Если решишь добавить пример, сравни, легче ли теперь понять твой аргумент. Если уточнишь вывод, проверь, ясно ли, какую мысль должен запомнить слушатель. Записи и разборы сохраняются в истории, чтобы ты мог вернуться к предыдущей попытке.</p></div></details>
      </div>
    </section>
    <section class="landing-final" aria-labelledby="final-title"><div><p class="landing-kicker">Перед важным днём есть время попробовать</p><h2 id="final-title">Отрепетируй своё выступление</h2><p>Время выступления выбираешь ты. Запиши речь на свою тему и получи разбор.</p>${startLink("Начать тренировку", "primary landing-cta")}</div></section>`,
    "landing",
  );
  landingCleanup = mountLandingMotion(document.querySelector(".landing"));
}
function landingContextIcon(key) {
  const paths = { speech: '<rect x="10" y="4" width="12" height="18" rx="6"/><path d="M6 16a10 10 0 0 0 20 0M16 26v4M11 30h10"/>', defense: '<rect x="4" y="6" width="24" height="18" rx="3"/><path d="M10 13h12M10 18h8M16 24v6M11 30h10"/>', free: '<path d="M4 14v4M10 8v16M16 3v26M22 8v16M28 14v4"/>' };
  return `<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${paths[key]}</svg>`;
}
function landingContextCopy(key) {
  const copy = {
    speech: ["Сделай главную мысль понятной слушателю", "Запиши своё выступление. После записи увидишь вопросы и разбор, которые опираются на твою речь."],
    defense: ["Объясни идею и подготовься к вопросам", "Отрепетируй защиту своего проекта. Вопросы и обратная связь будут относиться к тому, что ты расскажешь."],
    free: ["Потренируй тему, которую выберешь сам", "Выбери свободную речь и свою тему. Это может быть знакомство, обсуждение идеи или история, которую хочется рассказать понятнее."],
  };
  const [title, description] = copy[key];
  return `<h3>${title}</h3><p>${description}</p>`;
}
function authScreen(mode) {
  const register = mode === "register",
    reset = mode === "reset";
  frame(
    `<div class="auth-layout"><div class="auth-intro"><p class="eyebrow">${reset ? "Восстановление доступа" : "Репетиция начинается здесь"}</p><h1>${reset ? "Вернись к своим тренировкам" : state.guest?.blob && !reset ? "Получи разбор своего выступления" : register ? "Подготовься к своему выступлению" : "Продолжи свою тренировку"}</h1><p>${reset ? "Организатор выдаёт одноразовый код после проверки владельца аккаунта." : register ? (state.guest?.blob ? "Твоя запись уже готова. После регистрации перенесём её в аккаунт и подготовим разбор. Повторять выступление не нужно." : "После регистрации выбери тему и время выступления, запиши речь и получи разбор.") : state.guest?.blob ? "Войди, чтобы получить разбор уже записанного выступления. Запись перейдёт в твой аккаунт." : state.authReturn ? "После входа вернёмся к незавершённой тренировке. Сохранённые записи повторять не нужно." : "Твои записи и разборы останутся в истории."}</p></div><section class="auth-panel"><h2>${reset ? "Новый пароль" : register ? "Регистрация" : "Войди в аккаунт"}</h2><form id="auth-form" data-mode="${mode}">${register ? '<label>Имя<input name="name" autocomplete="given-name" maxlength="80" required></label>' : ""}${reset ? '<label>Одноразовый код<input name="token" autocomplete="off" required></label>' : '<label>Электронная почта<input type="email" name="email" autocomplete="email" maxlength="254" required></label>'}<div class="field-group"><label>${reset ? "Новый пароль" : "Пароль"}<input type="password" name="password" autocomplete="${register || reset ? "new-password" : "current-password"}" ${register || reset ? 'minlength="10"' : ""} maxlength="128" required></label>${register || reset ? '<p class="field-hint">Не менее 10 символов.</p>' : ""}</div>${register ? `<label>Для чего тренируешься?<select name="role"><option value="student">Учёба и защита проекта</option><option value="professional">Работа и выступления</option><option value="other">Другое</option></select></label>` : ""}<div class="form-error" role="alert"></div><button class="button primary" type="submit">${reset ? "Сохранить пароль" : register ? "Регистрация" : "Войти"}</button></form><p class="auth-links">${reset ? '<a href="#/login">Вернуться ко входу</a>' : register ? 'Уже есть аккаунт? <a href="#/login">Войти</a>' : '<a href="#/register">Регистрация</a> · <a href="#/reset">Восстановить доступ</a>'}</p></section></div>`,
  );
  if(mode === "login" && state.adminReturn && !state.guest?.blob && !state.authReturn)
    document.querySelector(".auth-intro").innerHTML = "<h1>Статистика сервиса</h1>";
}
async function persistGuest() {
  const { blob, config, createdAt, clientKey, serverPracticeId, ownerId } =
    state.guest;
  try {
    await saveDraft({
      blob,
      config,
      createdAt,
      clientKey,
      serverPracticeId,
      ownerId,
      durationSeconds: state.guest.durationSeconds,
      interrupted: state.guest.interrupted || false,
    });
    state.guestPersisted = true;
  } catch {
    state.guestPersisted = false;
  }
}

function rememberReturn(practiceId, ownerId = state.user?.id) {
  state.authReturn = { practiceId, ownerId };
  try {
    sessionStorage.setItem("practice-return", JSON.stringify(state.authReturn));
  } catch {}
}

function forgetReturn() {
  state.authReturn = null;
  try {
    sessionStorage.removeItem("practice-return");
  } catch {}
}

function writeRecordingDraft(pending, config) {
  const draft = {
    blob: pending.blob,
    ownerId: pending.ownerId,
    practiceId: pending.practiceId,
    kind: pending.kind,
    index: pending.index,
    createdAt: pending.createdAt,
    clientKey: pending.clientKey,
    durationSeconds: pending.durationSeconds,
    interrupted: pending.interrupted || false,
    autoSave: pending.autoSave || false,
    config,
  };
  const write = state.draftWrites.then(() =>
    pending.practiceId === "guest"
      ? saveDraft(draft)
      : saveRecordingDraft(draft),
  );
  state.draftWrites = write.catch(() => {});
  return write.then(
    () => true,
    () => false,
  );
}

async function persistPending(pending = state.pending) {
  if (!pending) return false;
  const saved = await writeRecordingDraft(pending, state.practice.config);
  if (state.pending === pending) state.pendingPersisted = saved;
  return saved;
}

async function clearAcceptedDraft(pending) {
  await clearRecordingDraft(pending).catch(() => {});
  await clearDraft(pending.clientKey).catch(() => {});
  if (state.guest?.clientKey === pending.clientKey) {
    state.guest.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
    state.guest = null;
    state.guestPersisted = false;
  }
}

async function restorePending(p) {
  if (!state.user) return;
  const ownerId = state.user.id;
  for (const answer of queuedAnswers(p)) {
    if (!p.segments.some((segment) => Number(segment.index) === answer.index))
      p.segments.push({id: `local:${answer.clientKey}`, kind: "answer", index: answer.index,
        duration_seconds: answer.durationSeconds, client_key: answer.clientKey, local_pending: true});
  }
  if (
    state.pending?.ownerId !== state.user.id ||
    state.pending?.practiceId !== p.id
  ) {
    discardPending();
    const drafts = await loadRecordingDrafts(ownerId).catch(() => []);
    if (state.user?.id !== ownerId || state.practice?.id !== p.id) return;
    const boundGuest = state.guest;
    let accountDraft;
    let accepted = false;
    for (const draft of drafts.filter((d) => d.practiceId === p.id).sort((a, b) => a.index - b.index)) {
      const saved = p.segments.find((segment) => segment.kind === draft.kind &&
        Number(segment.index) === draft.index && !segment.local_pending);
      if (saved?.client_key === draft.clientKey) {
        await clearAcceptedDraft(draft);
        accepted = true;
      } else if (!state.answerQueue.some((answer) => answer.clientKey === draft.clientKey)) {
        accountDraft = draft;
        break;
      }
    }
    const draft =
      accountDraft ||
      (boundGuest?.ownerId === ownerId && boundGuest.serverPracticeId === p.id
        ? {
            ...boundGuest,
            practiceId: p.id,
            kind: "speech",
            index: 0,
            interrupted: false,
            autoSave: true,
          }
        : null);
    if (draft) {
      state.pending = { ...draft, restored: true, url: URL.createObjectURL(draft.blob) };
      state.pendingPersisted = !!accountDraft || state.guestPersisted;
    } else if (accepted) return true;
  }
  const pending = state.pending;
  if (!pending) return;
  const saved = p.segments.find(
    (s) => s.kind === pending.kind && Number(s.index) === pending.index,
  );
  if (saved?.client_key === pending.clientKey) {
    await clearAcceptedDraft(pending);
    discardPending();
    return true;
  } else if (saved || p.report || p.active_job) {
    pending.conflict = true;
  }
}

async function resumeAfterLogin() {
  // A local account recording must never be imported into a different account.
  const ownerId = state.user.id;
  if (!state.guest) {
    const guestDraft = await loadDraft().catch(() => null);
    if (guestDraft && (!guestDraft.ownerId || guestDraft.ownerId === ownerId))
      state.guest = guestFromDraft(guestDraft);
  }
  if (state.pending && state.pending.ownerId !== ownerId) discardPending();
  if (state.guest?.ownerId && state.guest.ownerId !== ownerId) {
    state.guest.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
    state.guest = null;
    state.guestPersisted = false;
  }
  const target = state.authReturn;
  if (target && (!target.ownerId || target.ownerId === ownerId)) {
    go(`/practice/${encodeURIComponent(target.practiceId)}`);
    return;
  }
  forgetReturn();
  if (
    state.guest?.blob &&
    (!state.guest.ownerId || state.guest.ownerId === ownerId)
  )
    await importGuest();
  else if(state.adminReturn){state.adminReturn=false;try{sessionStorage.removeItem("analytics-return")}catch{};go("/admin/analytics")}
  else go("/app");
}

function sessionExpired() {
  telemetry("reauthentication_needed",{},state.practice?.id);
  const ownerId =
    state.user?.id || state.pending?.ownerId || state.recordingOwnerId;
  if(route()==="/admin/analytics"||route()==="/admin/analytics/export"){state.adminReturn=true;try{sessionStorage.setItem("analytics-return","1")}catch{}}
  else if (state.practice?.id && state.practice.id !== "guest")
    rememberReturn(state.practice.id, ownerId);
  state.user = null;
  if(typeof analyticsActor==="function")analyticsActor(null);
  state.meetingPracticeId = null;
  state.liveCapture?.cancel();
  state.liveCapture = null;
  clearTimeout(state.poll);
  if (state.recording) {
    notify(
      "Нужно войти снова. Закончи запись — она останется доступна после входа.",
    );
    return;
  }
  if (queuedAnswers().length) {
    if (!state.recording) {
      meetingPage(state.practice);
      document.querySelector(".chat-next").innerHTML = answerQueueMessage(state.practice);
    }
    return;
  }
  if (state.pending || state.uploading) {
    const currentHeader = document.querySelector(".header");
    if (currentHeader) currentHeader.outerHTML = header();
    if (!state.uploading) showPending();
    return;
  }
  go("/login");
}
function guestResult(message = "") {
  const p = state.guest;
  state.practice = p;
  state.guestNotice = message;
  if (p.config.questions) return meetingPage(p, true);
  frame(
    `<div class="page-heading"><p class="eyebrow">Твоя первая попытка</p><h1>Запись готова к разбору</h1><p class="page-description">${state.user ? "Перенесём выступление в твой аккаунт и подготовим разбор." : "Создай аккаунт, чтобы получить полный разбор этого выступления. Запись уже готова, повторять её не нужно."}</p></div><div class="guest-result-layout"><section class="guest-recording"><p class="eyebrow">Тема выступления</p><h2>${heading(p.config.topic || "Твоя речь")}</h2><p class="caption">Записано ${time(Math.round(p.durationSeconds || 0))}</p>${playback(p.segments[0].media_url, p.blob.type.startsWith("video/"))}<a class="quiet-link" href="${escape(p.segments[0].media_url)}" download="моя-запись">Скачать копию записи</a><p class="field-hint">${state.guestPersisted ? "Запись сохранена. В течение суток можно вернуться и продолжить тренировку." : "Не удалось сохранить запись. Не закрывай страницу до завершения тренировки."}</p></section><section class="guest-unlock"><h2>Что будет в полном разборе</h2><ul><li>Главная мысль и структура выступления</li><li>Что уже получается — с цитатами из твоей речи</li><li>Конкретная рекомендация для повторной попытки</li></ul><p>${p.config.questions ? "После входа в чате появятся три вопроса по выступлению. Запиши ответы, чтобы получить полный разбор речи и ответов." : "Разбор опирается на твою речь."} Затем можно повторить тренировку с выбранным фокусом.</p>${message ? errorBox(message) : ""}<div class="actions">${button(state.user ? "Получить разбор" : "Регистрация", "guest-analyze")}${!state.user ? '<a class="quiet-link" href="#/login">Уже есть аккаунт? Войти</a>' : ""}${button("Записать заново", "guest-again", "secondary")}</div></section></div>`,
  );
}
async function importGuest() {
  const draft = state.guest;
  if (!draft?.blob || state.uploading) return;
  state.uploading = true;
  frame(
    '<div class="processing"><p class="eyebrow">Продолжаем твою тренировку</p><h1>Сохраняем выступление в аккаунт</h1><p role="status">Запись уже готова. Дождись сохранения записи.</p></div>',
  );
  try {
    let p = await api.createPractice({
      ...draft.config,
      idempotency_key: draft.clientKey,
    });
    draft.serverPracticeId = p.id;
    draft.ownerId = state.user.id;
    await persistGuest();
    await writeRecordingDraft(
      {
        ...draft,
        practiceId: p.id,
        kind: "speech",
        index: 0,
        interrupted: false,
        autoSave: true,
      },
      p.config,
    );
    if (!p.segments.some((s) => s.kind === "speech")) {
      try {
        await api.upload(
          p.id,
          draft.blob,
          "speech",
          0,
          undefined,
          undefined,
          draft.clientKey,
        );
      } catch (error) {
        if (error.status !== 409) throw error;
      }
      p = await api.practice(p.id);
      if (
        !p.segments.some(
          (s) => s.kind === "speech" && s.client_key === draft.clientKey,
        )
      )
        throw new Error(
          "Запись ещё не загружена. Попробуй продолжить ещё раз.",
        );
    }
    if (
      !p.segments.some(
        (s) => s.kind === "speech" && s.client_key === draft.clientKey,
      )
    )
      throw new Error(
        "В тренировке уже есть другая запись. Скачай исходную запись перед продолжением.",
      );
    await clearRecordingDraft({ ...draft, practiceId: p.id, index: 0 }).catch(
      () => {},
    );
    await clearDraft(draft.clientKey).catch(() => {});
    draft.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
    state.guest = null;
    state.guestPersisted = false;
    window.history.replaceState(
      null,
      "",
      `#/practice/${encodeURIComponent(p.id)}`,
    );
    if (p.report || p.active_job) practicePage(p);
    else await continueAfterSave(p);
  } catch (error) {
    guestResult(
      `Аккаунт готов, но продолжить пока не удалось. ${errorText(error)} Исходная запись не потерялась. Попробуй продолжить тренировку ещё раз.`,
    );
  } finally {
    state.uploading = false;
  }
}
function savedTopic() {
  try {
    return sessionStorage.getItem("practice-topic") || "";
  } catch {
    return "";
  }
}
function setupForm(guest) {
  return `<form id="setup-form" data-guest="${guest}" class="setup-form"><h2>Новая тренировка</h2><div class="field-group"><label><span class="label-title">Тема выступления <span class="optional">необязательно</span></span><input name="topic" maxlength="300" placeholder="О чём будешь говорить?" value="${escape(savedTopic())}" aria-describedby="topic-hint"></label><p class="field-hint" id="topic-hint">Тема поможет учесть замысел твоего выступления в разборе.</p></div><fieldset class="field-group"><legend>Время выступления</legend><div class="duration-fields"><label>Минуты<input type="number" name="minutes" min="0" max="10" step="1" value="3" inputmode="numeric" required aria-describedby="duration-hint"></label><label>Секунды<input type="number" name="seconds" min="0" max="59" step="1" value="0" inputmode="numeric" required aria-describedby="duration-hint"></label></div><p class="field-hint" id="duration-hint">От 30 секунд до 10 минут. Можно закончить раньше.</p></fieldset><details class="custom-setup"><summary>Дополнительные настройки</summary><div class="practice-options"><fieldset><legend>Сценарий</legend><div class="scenario-options"><label><input type="radio" name="scenario" value="speech" checked><span><strong>Выступление</strong><small>Речь для аудитории</small></span></label><label><input type="radio" name="scenario" value="defense"><span><strong>Защита проекта</strong><small>Идея и аргументы</small></span></label><label><input type="radio" name="scenario" value="free"><span><strong>Свободная речь</strong><small>Тема на твой выбор</small></span></label></div></fieldset><div class="field-group"><label class="check"><input type="checkbox" name="questions" checked aria-describedby="questions-hint"><span>Ответить на вопросы после выступления</span></label><p class="field-hint" id="questions-hint">Три вопроса, до минуты на каждый ответ. Это время не входит в выступление.</p></div><label><span class="label-title">На что обратить внимание <span class="optional">необязательно</span></span><textarea name="criteria" maxlength="2000" rows="3" placeholder="Например, понятны ли аргументы и вывод"></textarea></label></div></details><div class="form-error" role="alert"></div><button type="submit" class="button primary">Перейти к записи</button></form>`;
}
async function setup(guest = false) {
  const version = state.routeVersion;
  let continuation = "";
  if (!guest) {
    try {
      const [history, drafts] = await Promise.all([
        api.practices(),
        loadRecordingDrafts(state.user.id).catch(() => []),
      ]);
      if (version !== state.routeVersion || !state.user) return;
      const unfinished = history.items.filter((p) => !p.report);
      const local = drafts.filter(
        (d) => !history.items.some((p) => p.id === d.practiceId),
      );
      const items = [
        ...local.map((d) => ({ id: d.practiceId, config: d.config })),
        ...unfinished,
      ];
      if (items.length)
        continuation = `<section class="practice-continuation"><h2>Продолжи незавершённую тренировку</h2><div class="history-list">${items
          .slice(0, 3)
          .map(
            (p) =>
              `<article class="history-item"><div><h3>${heading(p.config.topic || "Тренировка")}</h3><p class="caption">${drafts.some((d) => d.practiceId === p.id) ? "Есть запись, которую нужно сохранить" : p.status === "processing" ? "Готовим разбор" : p.status === "failed" ? "Запись сохранена. Попробуй получить разбор ещё раз" : "Можно вернуться к следующему этапу"}</p></div><a class="button secondary" href="#/practice/${encodeURIComponent(p.id)}">Продолжить</a></article>`,
          )
          .join(
            "",
          )}</div><a class="quiet-link" href="#/history">Все тренировки</a></section>`;
    } catch {
      if (version !== state.routeVersion || !state.user) return;
      continuation = `<div class="notice">Не удалось проверить незавершённые тренировки. <a href="#/history">Открыть историю</a></div>`;
    }
  }
  frame(
    `<div class="page-heading"><p class="eyebrow">${guest || !state.user.onboarding_completed ? "Первая тренировка" : "Твоя тренировка"}</p><h1>Подготовь выступление</h1><p class="page-description">Выбери тему и время, запиши речь и получи разбор по сказанному.</p></div>${!state.providerReady ? '<div class="notice">Разбор пока недоступен. Ты можешь записать выступление и вернуться к нему позже.</div>' : ""}${continuation}<div class="setup-layout practice-setup-layout">${setupForm(guest)}<section class="first-guide"><h2>Как проходит тренировка</h2><ol><li><strong>Выступи</strong><p>Говори на свою тему. Запись завершится в выбранное время; можно закончить раньше.</p></li><li><strong>Ответь на вопросы</strong><p>Вопросы появятся по одному, а ответы сохранятся автоматически.</p></li><li><strong>Посмотри разбор</strong><p>Узнай, что уже получается и что можно попробовать в следующей попытке. Здесь же можно прослушать и скачать записи.</p></li></ol></section></div>`,
  );
}
function practiceProgress(p, stage) {
  const labels = p.config.questions
    ? ["Выступление", "Ответы на вопросы", "Разбор"]
    : ["Запись речи", "Разбор", "Повторная попытка"];
  const index =
    stage === "report"
      ? p.config.questions
        ? 2
        : 1
      : stage === "questions" || nextSegment(p)?.kind === "answer"
        ? 1
        : 0;
  return `<nav aria-label="Этапы тренировки"><ol class="practice-progress">${labels.map((label, i) => `<li${i === index ? ' aria-current="step"' : ""}>${label}</li>`).join("")}</ol></nav>`;
}
function primaryRecommendation(report) {
  const items = report.recommendations || [];
  if (Number(report.schema_version) >= 2) {
    const index = report.primary_recommendation_index;
    return Number.isInteger(index) && index >= 0 ? items[index] || null : null;
  }
  return items[0] || null;
}
function repeatChoices(report) {
  return (report.recommendations || []).map((item, index) => ({
    ...item, text: item.action || item.text || "", recommendationIndex: index,
  })).filter((item) => item.text);
}
function repeatPanel(p) {
  const recommendations = repeatChoices(p.report);
  if (!recommendations.length) return "";
  const chosen = recommendations.findIndex((item) => item.recommendationIndex === (p.report.recommendations || []).indexOf(primaryRecommendation(p.report)));
  return `<details class="next-attempt"><summary>Выбрать фокус повторной попытки</summary><p>Выбери рекомендацию, которую хочешь попробовать в следующем выступлении.</p><fieldset><legend>Фокус следующей попытки</legend><div class="focus-options">${recommendations.map((item, index) => `<label class="focus-option"><input type="radio" name="repeat-focus" value="${index}"${index === chosen ? " checked" : ""}><span><strong>${heading(item.title)}</strong><span class="focus-description">${escape(item.text)}</span></span></label>`).join("")}</div></fieldset><div class="actions">${button("Повторить с выбранным фокусом", "repeat-selected", "secondary")}</div></details>`;
}
async function history(offset = 0) {
  frame(
    '<p class="eyebrow">Твои тренировки</p><h1>История</h1><div class="loading" role="status">Открываем историю…</div>',
  );
  const version = state.routeVersion;
  try {
    const data = await api.practices(offset);
    if (version !== state.routeVersion) return;
    frame(
      `<div class="page-heading row"><div><p class="eyebrow">Твои тренировки</p><h1>История</h1></div><a class="button primary" href="#/app">Новая тренировка</a></div>${data.items.length ? `<div class="history-list">${data.items.map((p) => `<article class="history-item"><div><p class="caption">${escape(date(p.created_at))}</p><h2><a href="#/practice/${encodeURIComponent(p.id)}">${heading(p.config?.topic || "Тренировка")}</a></h2><span class="tag ${p.status === "ready" ? "green" : ""}">${{ draft: "Запись и подготовка", processing: "Готовим разбор", ready: "Разбор готов", failed: "Попробуй получить разбор ещё раз" }[p.status] || escape(p.status)}</span></div><div class="actions"><a class="button secondary" href="#/practice/${encodeURIComponent(p.id)}">${p.status === "ready" ? "Посмотреть разбор" : "Продолжить"}</a>${button("Удалить", "delete", "text", `data-id="${escape(p.id)}"`)}</div></article>`).join("")}</div>${`<div class="actions">${offset > 0 ? button("Предыдущие", "history-page", "secondary", `data-offset="${Math.max(0, offset - 30)}"`) : ""}${offset + data.items.length < data.total ? button("Следующие", "history-page", "secondary", `data-offset="${offset + 30}"`) : ""}</div>`}` : `<div class="empty"><h2>Здесь появится твоя первая попытка</h2><p>Запиши выступление. Сохранённая запись и разбор останутся в истории.</p><a class="button primary" href="#/app">Начать тренировку</a></div>`}`,
    );
  } catch (error) {
    if (version === state.routeVersion)
      frame(
        `<h1>История</h1>${errorBox(errorText(error))}${button("Попробовать ещё раз", "refresh", "secondary")}`,
      );
  }
}
function evidenceOrigin(item) {
  const rawIndex = item.segment_index ?? item.index;
  const index = rawIndex === undefined || rawIndex === null || rawIndex === "" ? null : Number(rawIndex);
  if (item.origin === "answer" || (index !== null && index > 0))
    return index > 0 ? `Ответ на вопрос ${index}` : "Ответ";
  return item.origin === "speech" || index === 0 ? "Выступление" : "Фрагмент записи";
}
function evidenceMarkup(item) {
  return item.evidence ? `<figure class="report-evidence"><figcaption>${escape(evidenceOrigin(item))}</figcaption><blockquote>${escape(item.evidence)}</blockquote></figure>` : "";
}
function findingMarkup(item, actionFirst = false) {
  const observation = item.observation || "";
  const explanation = !observation && item.text ? item.text : "";
  const action = item.action ? `<p class="report-action"><strong>Что попробовать</strong> ${escape(item.action)}</p>` : "";
  return `${actionFirst ? action : ""}${observation ? `<p>${escape(observation)}</p>` : ""}${explanation ? `<p>${escape(explanation)}</p>` : ""}${evidenceMarkup(item)}${actionFirst ? "" : action}${item.example ? `<div class="report-example"><strong>Возможная формулировка</strong><p>${escape(item.example)}</p></div>` : ""}`;
}
function criterionStatus(status, basis) {
  return { met: "Есть в записи", partial: "Частично", not_met: basis === "present" ? "Есть несоответствие критерию" : "Не найдено в тексте речи", unknown: "По этой записи нельзя оценить" }[status] || "По этой записи нельзя оценить";
}
function transcriptMarkup(report) {
  if (report.transcript_segments?.length)
    return report.transcript_segments.map((segment) => `<section class="transcript-segment"><h3>${escape(segment.kind === "speech" ? "Выступление" : `Ответ на вопрос ${segment.index}`)}</h3>${segment.question ? `<p class="transcript-question"><strong>Вопрос</strong> ${escape(segment.question)}</p>` : ""}<p>${escape(segment.text)}</p></section>`).join("");
  return `<p>${escape(report.transcript || "Расшифровка недоступна")}</p>`;
}
function reportMarkup(report) {
  const primary = primaryRecommendation(report);
  const legacy = Number(report.schema_version || 1) < 2;
  const main = primary
    ? `<h2>Фокус следующей попытки</h2><h3 class="insight-copy">${heading(primary.title)}</h3>${legacy && report.insight ? `<p>${escape(report.insight)}</p>` : ""}${findingMarkup(primary, !legacy)}`
    : `<h2>${legacy && report.insight ? "Главное в этой попытке" : "Эта попытка сохранена"}</h2><p class="insight-copy">${escape(legacy && report.insight ? report.insight : "Обоснованного фокуса для повтора пока нет. Можно прослушать запись и попробовать ещё раз.")}</p>`;
  const observations = [...(report.strengths || []).map((item) => reportItem(item, "strength")), ...(report.recommendations || []).filter((item) => item !== primary).map((item) => reportItem(item, "recommendation"))].join("");
  return `<section class="report-insight">${main}<div class="actions">${button(primary ? "Записать повторную попытку" : "Записать ещё одну попытку", "repeat")}</div></section>${observations ? `<section class="report-observations"><h2>Наблюдения по твоей речи</h2>${observations}</section>` : ""}${report.criteria?.length ? `<section class="report-section"><h2>Твои критерии</h2>${report.criteria.map((c) => `<article class="criterion"><h3>${heading(c.criterion)}</h3><p class="criterion-status">${criterionStatus(c.status, c.basis)}</p>${c.reason || c.text ? `<p>${escape(c.reason || c.text)}</p>` : ""}${evidenceMarkup(c)}</article>`).join("")}</section>` : ""}`;
}
function readableReport(report) {
  // Translate application-owned labels from saved reports; speech and findings
  // retain their original words, including technical topics chosen by the user.
  const labels = {
    "Объём расшифровки": "Слова в тексте речи",
    "Распознанный текст": "Текст речи",
    "По распознанному тексту": "Текст речи",
    "Речь и ответы без ожидания обработки": "Время выступления и ответов",
    "Слова / длительность записи; включает молчание": "С учётом времени молчания",
    "Расшифровка может содержать ошибки.": "Текст речи может отличаться от записи.",
    "По текстовой расшифровке нельзя оценить этот критерий.": "Этот критерий нельзя оценить по содержанию речи.",
    "В доступной расшифровке нет достаточного основания: возможен пропуск при распознавании.": "В тексте речи могут быть неточности. Для этого вывода недостаточно основания.",
  };
  return {
    ...report,
    metrics: (report.metrics || []).map((m) => ({
      ...m, title: labels[m.title] || m.title, label: labels[m.label] || m.label,
    })),
    limitations: (report.limitations || []).map((l) => labels[l] || l),
    criteria: (report.criteria || []).map((c) => ({ ...c, reason: labels[c.reason] || c.reason })),
  };
}
function reportText(p) {
  const report = readableReport(p.report);
  const primary = primaryRecommendation(report);
  const sections = ["Сцена без страха", p.config.topic || "Твоя тренировка", date(p.created_at)];
  const findingLines = (item) => [item.title, item.observation || item.text || "", item.evidence ? `${evidenceOrigin(item)}: «${item.evidence}»` : "", item.action ? `Что попробовать: ${item.action}` : "", item.example ? `Возможная формулировка: ${item.example}` : ""];
  if (primary) sections.push("", "Фокус следующей попытки", ...findingLines(primary));
  if (Number(report.schema_version || 1) < 2 && report.insight) sections.push("", "Главное в этой попытке", report.insight);
  else if (!primary) sections.push("", "Обоснованного фокуса для повтора пока нет.");
  for (const [label, items] of [["Уже получается", report.strengths], ["Что попробовать", (report.recommendations || []).filter((item) => item !== primary)]]) {
    if (!items?.length) continue;
    sections.push("", label);
    for (const item of items) sections.push(...findingLines(item));
  }
  if (report.criteria?.length) {
    sections.push("", "Твои критерии");
    for (const c of report.criteria) sections.push(c.criterion, criterionStatus(c.status, c.basis), c.reason || c.text || "", c.evidence ? `${evidenceOrigin(c)}: ${c.evidence}` : "");
  }
  if (report.metrics?.length) {
    sections.push("", "О записи");
    for (const item of report.metrics) sections.push(item.label || "", item.title, item.text);
  }
  sections.push("", "Как читать разбор", "Разбор помогает оценить содержание речи. Голос, жесты и эмоции здесь не оцениваются.", ...(report.limitations || []), "", "Текст речи");
  if (report.transcript_segments?.length) {
    for (const segment of report.transcript_segments) sections.push(segment.kind === "speech" ? "Выступление" : `Ответ на вопрос ${segment.index}`, segment.question ? `Вопрос: ${segment.question}` : "", segment.text);
  } else sections.push(report.transcript || "");
  return sections.filter((part) => part !== null && part !== undefined).join("\n");
}
function downloadReport(p) {
  const url = URL.createObjectURL(new Blob([reportText(p)], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "разбор-выступления.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function reportItem(item, cls) {
  return `<article class="report-item ${cls}"><p class="eyebrow">${cls === "strength" ? "Уже получается" : "Можно попробовать"}</p><h3>${heading(item.title)}</h3>${findingMarkup(item)}</article>`;
}
function reportPage(p) {
  if (!state.user) { go("/login"); return; }
  if(typeof observeReport==="function")observeReport(p);
  const report = readableReport(p.report);
  frame(`<div class="report-reading">${practiceProgress(p, "report")}<div class="page-heading"><p class="eyebrow">Разбор · ${escape(date(p.created_at))}</p><h1>${heading(p.config.topic || "Твоя тренировка")}</h1></div><p class="page-description">Обратная связь по твоему выступлению и ответам на вопросы.</p>${p.latest_job?.kind === "report" && p.latest_job.status === "failed" ? errorBox("Не удалось обновить разбор. Предыдущий разбор и записи сохранены.") : ""}${reportMarkup(report)}${repeatPanel(p)}<details class="report-detail transcript"><summary>Текст речи и записи</summary>${transcriptMarkup(report)}<h3>Твои записи</h3>${mediaMarkup(p)}</details><details class="report-detail"><summary>Как читать разбор</summary>${report.metrics?.length ? `<div class="report-metrics">${report.metrics.map((m) => `<article><span class="eyebrow">${escape(m.label)}</span><h3>${heading(m.title)}</h3><p>${escape(m.text)}</p></article>`).join("")}</div>` : ""}<p>Разбор помогает оценить содержание речи. Голос, жесты и эмоции здесь не оцениваются.</p>${report.limitations?.length ? `<ul>${report.limitations.map((l) => `<li>${escape(l)}</li>`).join("")}</ul>` : ""}</details><div class="actions report-actions">${button("Скачать разбор", "download-report", "secondary")}${report.provenance?.report_prompt_version !== CURRENT_REPORT_VERSION ? button("Обновить разбор", "refresh-report", "secondary") : ""}${button("Выбрать другую тему", "new-topic", "text")}</div><details class="report-detail"><summary>Оставить отзыв о разборе</summary><form id="feedback-form" class="feedback-form"><h2>Был ли разбор полезен?</h2><fieldset><legend>Оценка от 1 до 5</legend><div class="ratings">${[1, 2, 3, 4, 5].map((n) => `<label><input type="radio" name="rating" value="${n}" required><span>${n}</span></label>`).join("")}</div></fieldset><label><span class="label-title">Что стоит улучшить? <span class="optional">необязательно</span></span><textarea name="text" rows="3" maxlength="2000"></textarea></label><div class="form-error" role="alert"></div><button type="submit" class="button secondary">Отправить отзыв</button></form></details></div>`);
}
function playback(url, video = false) {
  const tag = video ? "video" : "audio";
  return `<${tag} class="recording-playback" controls preload="metadata"${video ? " playsinline" : ""} src="${escape(url)}"></${tag}>`;
}
function mediaMarkup(p) {
  return `<div class="media-list">${(p.segments || [])
    .map((segment) => {
      const url =
        segment.media_url ||
        `/api/practices/${encodeURIComponent(p.id)}/segments/${encodeURIComponent(segment.id)}/media`;
      return `<article><strong>${segment.kind === "speech" ? "Выступление" : `Ответ ${escape(segment.index)}`}</strong>${playback(url, segment.has_video)}<a href="${escape(url)}?download=true" download>Скачать запись</a></article>`;
    })
    .join("")}</div>`;
}
function nextSegment(p) {
  if (!(p.segments || []).some((s) => s.kind === "speech"))
    return { kind: "speech", index: 0 };
  if (p.config.questions && p.questions?.length) {
    for (let i = 1; i <= p.questions.length; i++)
      if (!p.segments.some((s) => s.kind === "answer" && Number(s.index) === i))
        return { kind: "answer", index: i };
  }
  return null;
}
function recordingLimit(p, segment) {
  const remaining = Math.max(
    0,
    780 -
      (p.segments || []).reduce(
        (sum, s) => sum + Number(s.duration_seconds || 0),
        0,
      ),
  );
  return segment.kind === "answer"
    ? Math.min(60, Math.floor(remaining))
    : Math.min(Math.round(Number(p.config.duration) * 60), 600);
}
function deviceIcon(kind) {
  const path =
    kind === "camera"
      ? '<rect x="3" y="6" width="12" height="12" rx="2"/><path d="m15 10 6-3v10l-6-3"/>'
      : '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>';
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${path}<path class="device-off" d="M3 3l18 18"/></svg>`;
}
function questionChat(p, segment, job) {
  const arrival =
    state.questionsJustReady === p.id &&
    p.questions?.length &&
    !state.seenQuestionChats.has(p.id);
  if (p.questions?.length) state.seenQuestionChats.add(p.id);
  const currentIndex = state.pending?.practiceId === p.id
    ? state.pending.index
    : segment?.index || p.questions?.length || 0;
  const messages = (p.questions || []).slice(0, currentIndex)
    .map((question, i) => {
      const answer = p.segments.find(
        (s) => s.kind === "answer" && Number(s.index) === i + 1,
      );
      return `<li class="chat-message${segment?.index === i + 1 ? " is-current" : ""}" style="--message-delay:${i * 60}ms"><span class="chat-author">${["Мария", "Алексей", "Ирина"][i] || "Участник"}</span><p>${escape(question)}</p>${answer ? `<div class="chat-reply"><span class="chat-answer-state" data-answer-index="${i + 1}">Ты · ${answer.local_pending ? "Ответ записан" : "Ответ сохранён"}</span></div>` : ""}</li>`;
    })
    .join("");
  const failed =
    (p.latest_job?.status === "failed" || p.status === "failed") &&
    !p.questions?.length;
  if (state.pending?.practiceId === p.id) {
    const pending = state.pending;
    const savedText = pending.kind === "answer" ? "Ответ записан" : "Выступление записано";
    return `<aside class="meeting-chat" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header>${messages ? `<ol class="chat-messages" aria-label="Чат встречи">${messages}</ol>` : ""}<div class="chat-next"><p role="status">${state.uploading ? (pending.kind === "answer" ? "Сохраняем ответ…" : "Сохраняем выступление…") : pending.interrupted ? "Запись прервалась. Восстановили сохранённый фрагмент — прослушай его перед продолжением." : `${savedText}. Осталось сохранить запись.`}</p>${!state.uploading ? `<p>${pendingPersistenceText()}</p>${pending.interrupted ? playback(pending.url, pending.blob.type.startsWith("video/")) : ""}${!state.user && pending.ownerId ? button("Войти и продолжить", "reauth") : `${button(pending.interrupted ? "Сохранить фрагмент и продолжить" : "Повторить сохранение", "save-record")}${button("Перезаписать", "discard-record", "secondary")}`}` : ""}</div></aside>`;
  }
  if (p.id === "guest" && p.blob) {
    return `<aside class="meeting-chat" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header><div class="chat-next"><p role="status">${p.interrupted ? "Запись прервалась. Восстановили сохранённый фрагмент." : `Выступление записано.`}</p>${p.interrupted ? playback(p.segments[0].media_url, p.blob.type.startsWith("video/")) : ""}<p>${state.user ? "Продолжи в своём аккаунте, чтобы получить вопросы и полный разбор." : "Создай аккаунт, чтобы получить вопросы по этой речи и полный разбор. Записывать заново не нужно."}</p>${state.guestNotice ? errorBox(state.guestNotice) : ""}${button(state.user ? "Продолжить тренировку" : "Регистрация", "guest-analyze")}${!state.user ? '<a href="#/login">Уже есть аккаунт? Войти</a>' : ""}${button("Перезаписать", "guest-again", "secondary")}<a href="${escape(p.segments[0].media_url)}" download="моя-запись">Скачать копию записи</a>${!state.guestPersisted ? "<p>Не удалось сохранить запись. Не закрывай страницу до сохранения.</p>" : ""}</div></aside>`;
  }
  return `<aside class="meeting-chat${arrival ? " chat-arrival" : ""}" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header><ol class="chat-messages" role="log" aria-label="Чат встречи" aria-live="polite" aria-relevant="additions">${messages}</ol><div class="chat-next">${job ? `<p id="job-status" role="status">${jobStage(job.stage, job.kind)}</p><p class="caption">Вопросы появятся здесь, когда будут готовы.</p><div id="poll-error" role="alert"></div>` : !p.questions?.length ? `<p>${state.providerReady ? "Выступление сохранено. Осталось подготовить вопросы." : "Вопросы пока недоступны. Выступление сохранено."}</p>${failed ? errorBox(errorText(p.latest_job?.error)) : ""}${button("Подготовить вопросы", "questions", "primary", state.providerReady ? "" : "disabled")}` : (!segment || !state.user) && queuedAnswers(p).length ? answerQueueMessage(p) : `<p>Вопрос ${segment?.index || currentIndex} из ${p.questions.length}</p>`}</div></aside>`;
}
function meetingPage(p, guest = false, job = null) {
  const pendingRecording = state.pending?.practiceId === p.id;
  const segment = pendingRecording ? null : nextSegment(p);
  const chat = !!(
    job ||
    pendingRecording ||
    (p.config.questions && p.segments?.some((s) => s.kind === "speech"))
  );
  const devicesAvailable = true;
  const canRecord = !!segment && !job && !state.uploading && (!!state.user || guest);
  const ready = canRecord && state.meetingPracticeId !== p.id;
  const content = `<div class="meeting-topbar"><a class="quiet-link" href="#${guest ? "/guest" : "/app"}">К тренировке</a><h1>${heading(p.config.topic || "Твоя речь")}</h1>${canRecord ? `<span class="meeting-time" id="record-timer" aria-label="Осталось времени">${time(recordingLimit(p, segment))}</span>` : '<span class="meeting-time">Вопросы</span>'}</div><div class="meeting-body${chat ? " has-chat" : ""}"><div class="meeting-scene"><img class="meeting-audience" src="/audience-meeting-v1.png" alt="Слушатели в переговорной"><div class="self-view" hidden><video id="camera-preview" autoplay muted playsinline aria-label="Твоё видео" hidden></video><span class="self-name">Ты</span></div></div>${chat ? questionChat(p, segment, job) : ""}</div><div class="meeting-toolbar"><div class="meeting-devices">${devicesAvailable ? `<button class="device-control" type="button" data-action="toggle-mic" aria-pressed="false" title="Включить микрофон" ${state.uploading ? "disabled" : ""}>${deviceIcon("mic")}<span>Микрофон</span></button><button class="device-control" type="button" data-action="toggle-camera" aria-pressed="false" title="Включить камеру">${deviceIcon("camera")}<span>Камера</span></button>` : ""}</div><div class="meeting-controls" id="record-controls">${ready ? button("Я готов приступать", "start-record") : ""}</div><p class="meeting-status" id="record-status" role="status">${pendingRecording ? (state.uploading ? "Сохраняем запись…" : "Запись ещё не сохранена") : ready ? "Начни, когда будешь готов" : canRecord ? "Следующий вопрос" : "Выступление сохранено"}</p><div id="record-error" role="alert"></div><p id="camera-status" role="status"></p></div>`;
  const current = document.querySelector("#main.meeting");
  if (current?.dataset.practiceId === p.id) {
    const template = document.createElement("template");
    template.innerHTML = content;
    current
      .querySelector(".meeting-topbar")
      .replaceWith(template.content.querySelector(".meeting-topbar"));
    current
      .querySelector(".meeting-toolbar")
      .replaceWith(template.content.querySelector(".meeting-toolbar"));
    const body = current.querySelector(".meeting-body");
    const oldChat = body.querySelector(".meeting-chat");
    const newChat = template.content.querySelector(".meeting-chat");
    if (oldChat && newChat) oldChat.replaceWith(newChat);
    else if (newChat) body.append(newChat);
    else oldChat?.remove();
    body.classList.toggle("has-chat", chat);
  } else {
    frame(content, "meeting");
    document.querySelector("#main").dataset.practiceId = p.id;
  }
  updateCameraUI();
  updateMicUI();
}
function practicePage(p, guest = false) {
  state.practice = p;
  if (
    state.pending?.practiceId === p.id &&
    state.pending?.ownerId === state.user?.id
  )
    return showPending();
  const active = p.active_job || p.latest_job;
  if (active && ["pending", "running"].includes(active.status))
    return processingPage(p, active);
  if (p.report) {
    closeMedia();
    return reportPage(p);
  }
  if (guest && p.blob) return guestResult();
  if (queuedAnswers(p).length && !nextSegment(p)) {
    meetingPage(p, guest);
    return;
  }
  const segment = nextSegment(p);
  const needQuestions =
    p.config.questions &&
    p.segments?.some((s) => s.kind === "speech") &&
    !p.questions?.length;
  if (segment || needQuestions) {
    meetingPage(p, guest);
    if (segment?.kind === "answer") startNextAnswer(p);
    return;
  }
  frame(
    `${practiceProgress(p, "report")}<section class="empty"><h1>Записи сохранены</h1><p>Всё готово для разбора выступления.</p>${active?.status === "failed" ? errorBox(errorText(active.error)) : ""}${button("Получить разбор", "report", "primary", state.providerReady ? "" : "disabled")}${!state.providerReady ? '<p class="caption">Разбор пока недоступен. Записи сохранены в истории.</p>' : ""}</section>`,
  );
}
function jobStage(_stage, kind = "report") {
  return kind === "questions" ? "Готовим вопросы по твоей речи" : "Готовим разбор выступления";
}
function processingPage(p, job) {
  if (job.kind === "questions") {
    meetingPage(p, false, job);
    pollJob(p.id, job.id);
    return;
  }
  closeMedia();
  frame(
    `${practiceProgress(p, job.kind)}<div class="processing"><span class="spinner" aria-hidden="true"></span><p class="eyebrow">Записи сохранены</p><h1>${job.kind === "questions" ? "Готовим вопросы по твоей речи" : "Готовим разбор выступления"}</h1><p class="caption" id="job-status" role="status">Можно закрыть страницу. Готовый разбор появится в истории тренировок.</p><a href="#/history" class="button secondary">Открыть историю</a><div id="poll-error" role="alert"></div></div>`,
  );
  pollJob(p.id, job.id);
}
function pollJob(practiceId, jobId) {
  clearTimeout(state.poll);
  const version = state.routeVersion;
  const tick = async () => {
    try {
      const job = await api.job(jobId);
      if (version !== state.routeVersion) return;
      if (["succeeded", "failed"].includes(job.status)) {
        state.practice = await api.practice(practiceId);
        if (version !== state.routeVersion) return;
        if (job.kind === "questions" && job.status === "succeeded")
          state.questionsJustReady = practiceId;
        practicePage(state.practice);
        return;
      }
      const status = document.querySelector("#job-status");
      if (status && job.kind === "questions") status.textContent = jobStage(job.stage, job.kind);
      document.querySelector("#poll-error").textContent = "";
      state.poll = setTimeout(tick, 1800);
    } catch (error) {
      if (version !== state.routeVersion) return;
      document.querySelector("#poll-error").textContent =
        `${errorText(error)} Проверим состояние ещё раз.`;
      state.poll = setTimeout(tick, 5000);
    }
  };
  state.poll = setTimeout(tick, 1800);
}
async function checkMic() {
  const version = state.routeVersion;
  let stream = null;
  let context = null;
  let raf = null;
  const ownsMedia = () =>
    (!stream || state.stream === stream) &&
    (!context || state.audioContext === context);
  const releaseMedia = () => {
    stream?.getTracks().forEach((track) => track.stop());
    if (state.stream === stream) state.stream = null;
    if (context && context.state !== "closed")
      void context.close().catch(() => {});
    if (state.audioContext === context) state.audioContext = null;
    if (raf !== null) cancelAnimationFrame(raf);
    if (state.raf === raf) state.raf = null;
  };
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw new Error(
        "Запись не открылась. Попробуй открыть сайт в Chrome, Safari или Firefox.",
      );
    closeMedia({ keepCamera: true });
    updateMicUI();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });
    if (version !== state.routeVersion) {
      releaseMedia();
      return;
    }
    state.stream = stream;
    telemetry("device_access_result",{device_kind:"microphone",result:"granted"},state.practice?.id);
    const Context = window.AudioContext || window.webkitAudioContext;
    if (Context) {
      context = new Context();
      state.audioContext = context;
      await context.resume();
      if (version !== state.routeVersion || !ownsMedia()) {
        releaseMedia();
        return;
      }
      const source = context.createMediaStreamSource(stream),
        analyser = context.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const draw = () => {
        if (version !== state.routeVersion || !ownsMedia()) return;
        analyser.getByteTimeDomainData(samples);
        let power = 0;
        for (const x of samples) power += (x - 128) ** 2;
        const level = Math.min(1, Math.sqrt(power / samples.length) / 30);
        const meter = document.querySelector("#sound-level");
        if (meter) meter.style.transform = `scaleX(${level})`;
        raf = requestAnimationFrame(draw);
        state.raf = raf;
      };
      draw();
      if (
        state.user &&
        state.providerReady &&
        state.practice?.id !== "guest" &&
        nextSegment(state.practice)?.kind === "speech"
      ) {
        const capture = new LiveAudioCapture({
          context,
          stream,
          api,
          practiceId: state.practice.id,
        });
        state.liveCapture = capture;
        try {
          const ready = await capture.bounded(capture.prepare(), 2500);
          if (!ready) throw new Error("Worklet preparation timeout");
        } catch {
          capture.cancel();
          if (state.liveCapture === capture) state.liveCapture = null;
        }
        if (version !== state.routeVersion || !ownsMedia()) {
          capture.cancel();
          releaseMedia();
          return;
        }
      }
    }
    const status = document.querySelector("#record-status");
    if (status) status.textContent = "Можно начинать";
    updateMicUI();
    const errorPanel = document.querySelector("#record-error");
    if (errorPanel) errorPanel.textContent = "";
  } catch (error) {
    const owned = ownsMedia();
    telemetry("device_access_result",{device_kind:"microphone",result:error.name==="NotAllowedError"?"denied":"unavailable"},state.practice?.id);
    releaseMedia();
    if (version !== state.routeVersion || !owned) return;
    updateMicUI();
    const errorPanel = document.querySelector("#record-error");
    if (!errorPanel) return;
    errorPanel.innerHTML = errorBox(
      error.name === "NotAllowedError"
        ? "Доступ к микрофону закрыт. Разреши его в настройках сайта и повтори проверку."
        : error.name === "NotFoundError"
          ? "Микрофон не найден. Подключи устройство и повтори проверку."
          : errorText(error),
    );
  }
}
function cameraLive() {
  return state.cameraStream
    ?.getVideoTracks()
    .some((t) => t.readyState === "live" && t.enabled);
}
function updateMicUI() {
  const tracks = state.stream?.getAudioTracks() || [];
  const live = tracks.some((t) => t.readyState === "live" && t.enabled);
  const control = document.querySelector('[data-action="toggle-mic"]');
  if (control) {
    control.setAttribute("aria-pressed", String(live));
    control.title = live ? "Выключить микрофон" : "Включить микрофон";
  }
  const start = document.querySelector('[data-action="start-record"]');
  if (start) start.disabled = state.cameraBusy;
}
async function toggleMic() {
  const tracks =
    state.stream?.getAudioTracks().filter((t) => t.readyState === "live") || [];
  if (!tracks.length) return checkMic();
  const enabled = !tracks.some((t) => t.enabled);
  tracks.forEach((t) => {
    t.enabled = enabled;
  });
  updateMicUI();
  document.querySelector("#record-status").textContent = enabled
    ? state.recording
      ? "Идёт запись"
      : "Можно начинать"
    : "Микрофон выключен";
  if (enabled && !state.recording) startNextAnswer(state.practice);
}
function updateCameraUI() {
  const start = document.querySelector('[data-action="start-record"]');
  if (start) start.disabled = state.cameraBusy;
  const control = document.querySelector('[data-action="toggle-camera"]');
  if (control) {
    control.disabled =
      state.cameraBusy || (state.recording && !state.recordingWithVideo);
    control.setAttribute("aria-pressed", String(!!cameraLive()));
    control.title = state.cameraBusy
      ? "Подключаем камеру…"
      : cameraLive()
        ? "Выключить камеру"
        : "Включить камеру";
  }
  const preview = document.querySelector("#camera-preview");
  if (preview) {
    preview.hidden = !cameraLive();
    const stream = cameraLive() ? state.cameraStream : null;
    if (preview.srcObject !== stream) preview.srcObject = stream;
    preview.closest(".self-view").hidden = !cameraLive();
  }
}
function closeCamera() {
  state.cameraVersion += 1;
  state.cameraStream?.getTracks().forEach((t) => t.stop());
  state.cameraStream = null;
  state.cameraBusy = false;
  const status = document.querySelector("#camera-status");
  if (status) status.textContent = "";
  updateCameraUI();
}
async function toggleCamera() {
  if (state.cameraBusy) return;
  const status = document.querySelector("#camera-status");
  if (state.recording) {
    if (!state.recordingWithVideo) return;
    const enabled = !cameraLive();
    state.cameraStream?.getVideoTracks().forEach((t) => {
      t.enabled = enabled;
    });
    updateCameraUI();
    return;
  }
  if (cameraLive()) {
    closeCamera();
    status.textContent = "";
    return;
  }
  const routeVersion = state.routeVersion;
  const cameraVersion = ++state.cameraVersion;
  state.cameraBusy = true;
  updateCameraUI();
  try {
    if (!navigator.mediaDevices?.getUserMedia)
      throw new Error("Не удалось подключить камеру. Можно продолжить со звуком.");
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 360 },
        frameRate: { ideal: 24, max: 24 },
        facingMode: "user",
      },
      audio: false,
    });
    if (
      routeVersion !== state.routeVersion ||
      cameraVersion !== state.cameraVersion ||
      state.recording
    ) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    telemetry("device_access_result",{device_kind:"camera",result:"granted"},state.practice?.id);
    state.cameraStream = stream;
    stream.getVideoTracks().forEach((t) =>
      t.addEventListener("ended", () => {
        updateCameraUI();
        if (!cameraLive())
          status.textContent =
            "Камера отключилась. Можно продолжить со звуком.";
      }),
    );
    status.textContent = "";
  } catch (error) {
    if (
      routeVersion !== state.routeVersion ||
      cameraVersion !== state.cameraVersion
    )
      return;
    telemetry("device_access_result",{device_kind:"camera",result:error.name==="NotAllowedError"?"denied":"unavailable"},state.practice?.id);
    status.textContent =
      error.name === "NotAllowedError"
        ? "Доступ к камере закрыт. Разреши его в настройках сайта или продолжи со звуком."
        : error.name === "NotFoundError"
          ? "Камера не найдена. Можно продолжить со звуком."
          : "Не удалось подключить камеру. Можно продолжить со звуком.";
  } finally {
    if (cameraVersion === state.cameraVersion) {
      state.cameraBusy = false;
      updateCameraUI();
    }
  }
}
function closeMedia({
  keepCamera = false,
  keepLive = false,
  keepStream = false,
} = {}) {
  if (!keepStream && !keepLive) state.meetingPracticeId = null;
  if (!keepCamera) closeCamera();
  clearInterval(state.timer);
  if (keepLive) return;
  state.liveCapture?.cancel();
  state.liveCapture = null;
  if (keepStream) return;
  cancelAnimationFrame(state.raf);
  state.stream?.getTracks().forEach((t) => t.stop());
  state.stream = null;
  if (state.audioContext) {
    void state.audioContext.close().catch(() => {});
    state.audioContext = null;
  }
}
function microphoneReady() {
  return state.stream
    ?.getAudioTracks()
    .some((t) => t.readyState === "live" && t.enabled);
}
async function beginMeeting() {
  if (state.recording || state.pending || state.uploading || state.cameraBusy) return;
  const p = state.practice, version = state.routeVersion;
  const tracks = state.stream
    ?.getAudioTracks().filter((t) => t.readyState === "live") || [];
  if (tracks.length) tracks.forEach((t) => { t.enabled = true; });
  else await checkMic();
  if (version !== state.routeVersion || state.practice?.id !== p.id || !microphoneReady()) return;
  state.meetingPracticeId = p.id;
  if (nextSegment(p)?.kind === "answer") startNextAnswer(p);
  else startRecording();
}
function startNextAnswer(p) {
  const segment = nextSegment(p);
  if (
    state.meetingPracticeId !== p.id || segment?.kind !== "answer" ||
    state.recording || state.pending || state.uploading || !state.user
  ) return;
  if (!microphoneReady()) {
    document.querySelector("#record-status").textContent = "Включи микрофон, чтобы продолжить ответ";
    document.querySelector("#record-controls").innerHTML = button("Продолжить тренировку", "start-record");
    return;
  }
  document.querySelector(".chat-message.is-current")?.scrollIntoView({ block: "nearest", behavior: "instant" });
  startRecording();
}

function queuedAnswers(p = state.practice) {
  return state.answerQueue.filter((answer) => answer.practiceId === p?.id &&
    (!state.user || answer.ownerId === state.user.id));
}
function answerQueueMessage(p) {
  const answers = queuedAnswers(p);
  if (!answers.length) return "";
  if (!state.user)
    return `<p>Ответы записаны. Войди снова, чтобы сохранить их и получить разбор.</p>${button("Войти и продолжить", "reauth-answers")}`;
  if (answers.some((answer) => answer.error))
    return `<p role="alert">Не удалось сохранить все ответы. Записи остаются доступными; повтори сохранение.</p>${button("Повторить сохранение", "retry-answers")}`;
  return '<p role="status">Ответы записаны. Сохраняем их и готовим разбор…</p>';
}
function updateAnswerProgress(p) {
  if (state.practice !== p) return;
  for (const segment of p.segments.filter((s) => s.kind === "answer")) {
    const label = document.querySelector(`[data-answer-index="${segment.index}"]`);
    if (label) label.textContent = segment.local_pending ? "Ты · Ответ записан" : "Ты · Ответ сохранён";
  }
  // A background acknowledgement must never replace an active recorder's DOM.
  if (state.recording || state.pending || (state.user && nextSegment(p))) return;
  const panel = document.querySelector(".chat-next");
  if (panel) panel.innerHTML = answerQueueMessage(p);
}
function enqueueAnswer(p, answer) {
  answer.persisted = false;
  answer.persistence = writeRecordingDraft(answer, p.config).then((saved) => {
    answer.persisted = saved;
    if (!saved && state.practice === p && queuedAnswers(p).includes(answer))
      document.querySelector("#record-error").innerHTML = errorBox("Не закрывай страницу, пока ответы не сохранятся.");
    return saved;
  });
  state.answerQueue.push(answer);
  p.segments.push({ id: `local:${answer.clientKey}`, kind: "answer", index: answer.index,
    duration_seconds: answer.durationSeconds, client_key: answer.clientKey, local_pending: true });
  meetingPage(p);
  startNextAnswer(p);
  void pumpAnswerUploads(p);
}
async function pumpAnswerUploads(p) {
  if (state.answerPump || !state.user || !queuedAnswers(p).length) return;
  const ownerId = state.user.id, version = state.routeVersion;
  // Publish the promise before the first request so repeated clicks cannot create another uploader.
  const run = async () => {
    while (state.user?.id === ownerId) {
      const answer = queuedAnswers(p)[0];
      if (!answer || answer.error) break;
      let saved;
      telemetry("segment_upload_started",{capture_id:answer.clientKey,segment_index:answer.index},p.id);
      try {
        try {
          saved = await api.upload(p.id, answer.blob, "answer", answer.index,
            undefined, undefined, answer.clientKey);
        } catch (error) {
          if (error.status !== 409 || error.code === "UPLOAD_KEY_CONFLICT") throw error;
          const remote = await api.practice(p.id);
          saved = remote.segments.find((segment) => segment.kind === "answer" &&
            Number(segment.index) === answer.index && segment.client_key === answer.clientKey);
          if (!saved) throw error;
        }
        const index = p.segments.findIndex((segment) => segment.client_key === answer.clientKey);
        if (index !== -1) p.segments[index] = saved;
        state.answerQueue = state.answerQueue.filter((entry) => entry !== answer);
        // Wait for the local write before deleting it, while the next upload/answer proceeds.
        void answer.persistence.then(() => clearAcceptedDraft(answer));
        URL.revokeObjectURL(answer.url);
        if (version === state.routeVersion && state.practice === p && state.user?.id === ownerId)
          updateAnswerProgress(p);
      } catch (error) {
        telemetry("segment_upload_failed",{capture_id:answer.clientKey,segment_index:answer.index,error_code:error.code||"UPLOAD_FAILED"},p.id);
        answer.error = error;
        break;
      }
    }
  };
  state.answerPump = Promise.resolve().then(run);
  try { await state.answerPump; }
  finally {
    state.answerPump = null;
    if (version !== state.routeVersion || state.practice !== p) return;
    updateAnswerProgress(p);
    if (state.user?.id === ownerId && !state.recording && !state.pending &&
        !nextSegment(p) && !queuedAnswers(p).length)
      await continueAfterSave(p);
  }
}
function startRecording() {
  if (state.recording || state.pending || state.uploading) return;
  if (
    !state.stream ||
    state.stream.getAudioTracks().some((t) => t.readyState !== "live")
  ) {
    void checkMic();
    return;
  }
  const p = state.practice, segment = nextSegment(p), version = state.routeVersion;
  if (!segment) return;
  const duration = recordingLimit(p, segment);
  const withVideo = !!cameraLive();
  const types = withVideo
    ? ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"]
    : ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"];
  const type = types.find((t) => MediaRecorder.isTypeSupported(t));
  if (duration < 2) {
    closeMedia();
    document.querySelector("#record-error").innerHTML =
      errorBox(
        "Время тренировки закончилось. Можно получить разбор сохранённых записей.",
      ) + button("Получить разбор", "report", "secondary");
    return;
  }
  const chunks = [];
  const ownerId = p.id === "guest" ? null : state.user?.id;
  if (p.id !== "guest" && !ownerId) {
    rememberReturn(p.id);
    go("/login");
    return;
  }
  state.recordingOwnerId = ownerId;
  const clientKey = crypto.randomUUID().replaceAll("-", "");
  const createdAt = Date.now();
  let lastCheckpoint = createdAt;
  state.recordingError = "";
  try {
    const recorder = new MediaRecorder(
      new MediaStream([
        ...state.stream.getAudioTracks(),
        ...(withVideo ? state.cameraStream.getVideoTracks() : []),
      ]),
      {
        ...(type ? { mimeType: type } : {}),
        ...(withVideo
          ? { videoBitsPerSecond: 300000, audioBitsPerSecond: 64000 }
          : {}),
      },
    );
    state.recorder = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
      if (
        state.recording &&
        Date.now() - lastCheckpoint >= 5000 &&
        chunks.length
      ) {
        lastCheckpoint = Date.now();
        void writeRecordingDraft(
          {
            blob: new Blob(chunks, { type: recorder.mimeType || "audio/webm" }),
            ownerId,
            practiceId: p.id,
            clientKey,
            createdAt,
            kind: segment.kind,
            index: segment.index,
            durationSeconds: (Date.now() - state.started) / 1000,
            interrupted: true,
            autoSave: false,
          },
          p.config,
        ).then((saved) => {
          if (!saved && state.recording)
            document.querySelector("#record-error").innerHTML = errorBox(
              "Не удалось сохранить запись. Не закрывай страницу, пока она не сохранится.",
            );
        });
      }
    };
    recorder.onerror = () => {
      state.recordingError =
        "Запись прервалась из-за ошибки микрофона. Прослушай сохранённый фрагмент перед продолжением.";
    };
    recorder.onstop = async () => {
      telemetry(state.recordingError?"capture_interrupted":"capture_stopped",{capture_id:clientKey,segment_index:segment.index,elapsed_ms:Math.min(86400000,Math.max(0,Date.now()-state.started))},p.id);
      if(segment.kind==="answer")telemetry("answer_recorded",{capture_id:clientKey,question_index:segment.index},p.id);
      state.recording = false;
      clearInterval(state.timer);
      const blob = new Blob(chunks, {
        type: recorder.mimeType || "audio/webm",
      });
      state.pending = {
        blob,
        kind: segment.kind,
        index: segment.index,
        url: URL.createObjectURL(blob),
        practiceId: p.id,
        durationSeconds: Math.max(1, (Date.now() - state.started) / 1000),
        ownerId,
        clientKey,
        createdAt,
        interrupted: !!state.recordingError,
        autoSave: !state.recordingError,
      };
      state.pendingPersisted = false;
      const capture = state.liveCapture;
      state.liveCapture = null;
      if (capture && segment.kind === "speech") {
        state.pending.liveCompletion = capture.finish().finally(() => {
          if (state.audioContext === capture.context)
            closeMedia({ keepCamera: p.config.questions, keepStream: p.config.questions });
        });
      } else capture?.cancel();
      closeMedia({
        keepCamera: p.config.questions,
        keepStream: p.config.questions,
        keepLive: !!state.pending.liveCompletion,
      });
      if (segment.kind === "answer" && !state.recordingError && p.id !== "guest") {
        const answer = state.pending;
        state.pending = null;
        if (version === state.routeVersion && state.practice?.id === p.id) enqueueAnswer(p, answer);
        else void writeRecordingDraft(answer, p.config);
        return;
      }
      if (!state.recordingError && version === state.routeVersion && state.practice?.id === p.id)
        void saveRecording();
      else {
        await persistPending();
        if (version === state.routeVersion && state.practice?.id === p.id) showPending();
      }
    };
    recorder.start(1000);
    telemetry("capture_started",{capture_id:clientKey,segment_index:segment.index,camera_enabled:withVideo},p.id);
    if(segment.kind==="answer"){telemetry("question_presented",{question_index:segment.index},p.id);telemetry("answer_started",{capture_id:clientKey,question_index:segment.index},p.id)}
    state.recording = true;
    state.recordingWithVideo = withVideo;
    updateCameraUI();
    state.started = Date.now();
    document.querySelector("#record-status").textContent = "Идёт запись";
    if (segment.kind === "speech") state.liveCapture?.start();
    document.querySelector("#record-controls").innerHTML = button(
      segment.kind === "answer" ? "Завершить ответ" : "Завершить выступление",
      "stop-record",
      "danger",
    );
    state.timer = setInterval(() => {
      const elapsed = (Date.now() - state.started) / 1000;
      document.querySelector("#record-timer").textContent = time(
        Math.max(0, Math.ceil(duration - elapsed)),
      );
      if (elapsed >= Math.max(1, duration - 1)) stopRecording(true);
    }, 200);
  } catch (error) {
    document.querySelector("#record-error").innerHTML = errorBox(
      "Не удалось начать запись. Повтори проверку микрофона.",
    );
    closeMedia();
  }
}
function stopRecording(automatic = false) {
  if (state.recorder?.state === "recording") {
    if (automatic)
      document.querySelector("#record-timer").textContent = "00:00";
    state.recorder.stop();
  }
}
async function continueAfterSave(p, { restoreDrafts = false } = {}) {
  if (!state.user && p.id !== "guest") {
    rememberReturn(p.id);
    go("/login");
    return;
  }
  const version = state.routeVersion;
  if (queuedAnswers(p).length) { practicePage(p); return; }
  if (restoreDrafts) await restorePending(p);
  if (version !== state.routeVersion || state.practice?.id !== p.id) return;
  practicePage(p);
  if (state.pending) {
    if (state.pending.autoSave && !state.pending.interrupted && !state.pending.conflict)
      await saveRecording();
    return;
  }
  const kind =
    p.config.questions && !p.questions?.length
      ? "questions"
      : nextSegment(p)
        ? null
        : "report";
  if (!kind || !state.providerReady) return;
  try {
    const job = await api.startJob(p.id, kind);
    if (version !== state.routeVersion || state.practice?.id !== p.id) return;
    processingPage(p, job);
  } catch (error) {
    if (version !== state.routeVersion || state.practice?.id !== p.id) return;
    const panel =
      document.querySelector(".chat-next") || document.querySelector(".empty");
    if (panel)
      panel.insertAdjacentHTML(
        "beforeend",
        errorBox(
          `Запись сохранена. ${errorText(error)} Нажми «${kind === "questions" ? "Подготовить вопросы" : "Получить разбор"}», чтобы продолжить.`,
        ),
      );
  }
}
function showPending() {
  const pending = state.pending;
  if (!pending) return;
  if (pending.missing) {
    frame(
      `<section class="narrow record-review"><h1>Тренировка больше недоступна</h1><p>Твоя запись не потерялась. Скачай её, если хочешь сохранить копию.</p>${playback(pending.url, pending.blob.type.startsWith("video/"))}<a class="button secondary" href="${escape(pending.url)}" download="моя-запись">Скачать запись</a>${button("Удалить эту запись", "delete-local-draft", "text")}<a href="#/app">К тренировкам</a></section>`,
    );
    return;
  }
  if (pending.conflict) {
    frame(
      `<section class="narrow record-review"><h1>На этом этапе уже есть сохранённая запись</h1><p>Здесь сохранились две разные записи. Прослушай эту запись и при необходимости скачай её перед продолжением.</p>${playback(pending.url, pending.blob.type.startsWith("video/"))}<a class="button secondary" href="${escape(pending.url)}" download="моя-запись">Скачать запись</a>${button("Продолжить с сохранённой записью", "use-server-recording")}</section>`,
    );
    return;
  }
  meetingPage(state.practice, state.practice.id === "guest");
  if (state.recordingError)
    document.querySelector("#record-error").innerHTML = errorBox(
      state.recordingError,
    );
}
function discardPending() {
  if (state.pending) URL.revokeObjectURL(state.pending.url);
  state.pending = null;
  state.pendingPersisted = false;
}
function pendingPersistenceText() {
  return state.pendingPersisted
    ? "Запись сохранена на этом устройстве на сутки. Можно вернуться и продолжить тренировку."
    : "Запись ещё не сохранена. Не закрывай страницу и повтори сохранение.";
}
async function saveRecording() {
  if (!state.pending || state.uploading) return;
  const pending = state.pending,
    p = state.practice;
  if (pending.ownerId && state.user?.id !== pending.ownerId) {
    rememberReturn(p.id, pending.ownerId);
    showPending();
    return;
  }
  state.uploading = true;
  const needsPersist =
    !pending.autoSave || !state.pendingPersisted || pending.interrupted;
  pending.autoSave = true;
  pending.interrupted = false;
  const persistence = needsPersist ? persistPending(pending) : Promise.resolve(state.pendingPersisted);
  meetingPage(p, p.id === "guest");
  try {
    if (p.id === "guest") {
      await persistence;
      p.blob = pending.blob;
      p.durationSeconds = pending.durationSeconds;
      p.createdAt = pending.createdAt;
      p.clientKey = pending.clientKey;
      p.interrupted = false;
      p.segments = [{ kind: "speech", index: 0, media_url: pending.url }];
      state.guest = p;
      state.guestPersisted = state.pendingPersisted;
      state.pending = null;
      state.pendingPersisted = false;
      guestResult();
      return;
    }
    const live = pending.liveCompletion ? await pending.liveCompletion : null;
    const upload = (session) =>
      api.upload(
        p.id,
        pending.blob,
        pending.kind,
        pending.index,
        session?.sessionId,
        session?.chunkCount,
        pending.clientKey,
      );
    let saved;
    telemetry("segment_upload_started",{capture_id:pending.clientKey,segment_index:pending.index},p.id);
    try {
      saved = await upload(live);
    } catch (error) {
      if (error.code !== "LIVE_SESSION_STALE") throw error;
      // This rejection happens before the server stores a segment.
      pending.liveCompletion = null;
      saved = await upload(null);
    }
    if (!p.segments.some((s) => s.id === saved.id)) p.segments.push(saved);
    p.status = "draft";
    p.latest_job = null;
    const cleanup = persistence.then(() => clearAcceptedDraft(pending));
    discardPending();
    const keepDevices = p.config.questions && (!!nextSegment(p) || !p.questions?.length);
    closeMedia({ keepCamera: keepDevices, keepStream: keepDevices });
    state.uploading = false;
    await Promise.all([cleanup, continueAfterSave(p, {restoreDrafts: !!pending.restored})]);
  } catch (error) {
    if (error.status === 409 && error.code !== "UPLOAD_KEY_CONFLICT") {
      try {
        const saved = await api.practice(p.id);
        if (
          saved.segments.some(
            (s) =>
              s.kind === pending.kind &&
              Number(s.index) === pending.index &&
              s.client_key === pending.clientKey,
          )
        ) {
          await clearAcceptedDraft(pending);
          discardPending();
          state.uploading = false;
          await continueAfterSave(saved, {restoreDrafts: !!pending.restored});
          return;
        }
      } catch {}
    }
    await persistence;
    state.uploading = false;
    showPending();
    document.querySelector("#record-error").innerHTML = errorBox(
      `${errorText(error)} ${pendingPersistenceText()}`,
    );
  } finally {
    state.uploading = false;
  }
}
async function navigate() {
  const path = route();
  const resumingAnswers = path === `/practice/${encodeURIComponent(state.practice?.id)}` &&
    !state.recording && !state.answerPump;
  if (queuedAnswers().length && !resumingAnswers && !["/login", "/register", "/reset"].includes(path)) {
    notify("Сначала сохрани ответы, чтобы продолжить.");
    window.history.replaceState(null, "", `#/practice/${encodeURIComponent(state.practice.id)}`);
    return;
  }
  if (state.recording || state.pending || state.uploading) {
    if (state.uploading) {
      notify("Дождись сохранения записи.");
      window.history.replaceState(
        null,
        "",
        `#${state.practice.id === "guest" ? "/guest" : "/practice/" + encodeURIComponent(state.practice.id)}`,
      );
      return;
    }
    if (
      (state.recording || !state.pendingPersisted) &&
      !confirm(
        "Несохранённая запись будет потеряна при переходе на другую страницу. Перейти?",
      )
    ) {
      window.history.replaceState(
        null,
        "",
        `#${state.practice.id === "guest" ? "/guest" : "/practice/" + encodeURIComponent(state.practice.id)}`,
      );
      return;
    }
    if (state.recording) {
      state.recorder.onstop = null;
      state.recorder.stop();
      state.recording = false;
    }
    if (!["/login", "/register", "/reset"].includes(path)) discardPending();
  }
  closeMedia();
  clearTimeout(state.poll);
  window.scrollTo({ top: 0, behavior: "instant" });
  const version = ++state.routeVersion;
  if (path === "/landing") {if(typeof trackPage==="function")trackPage(path);return landing()}
  if (path === "/example") return go("/landing");
  if (path === "/privacy") return go("/landing");
  if (["/register", "/login", "/reset"].includes(path)) {
    if (state.user && path !== "/reset") {
      if (state.guest?.blob) return guestResult();
      go("/app");
      return;
    }
    if(typeof trackPage==="function")trackPage(path);
    authScreen(path.slice(1));
    return;
  }
  if (path === "/guest") return go(state.user ? "/app" : "/register");
  if (!state.user) {
    if(path==="/admin/analytics"||path==="/admin/analytics/export"){state.adminReturn=true;try{sessionStorage.setItem("analytics-return","1")}catch{}}
    const pendingPractice = path.match(/^\/practice\/([a-f0-9]{32})$/);
    if (pendingPractice)
      rememberReturn(
        pendingPractice[1],
        state.authReturn?.practiceId === pendingPractice[1]
          ? state.authReturn.ownerId
          : undefined,
      );
    if (!state.online) {
      frame(
        `<h1>Не удалось подключиться</h1>${errorBox("Вход и сохранение пока недоступны. Попробуй подключиться ещё раз.")} ${button("Повторить подключение", "reconnect", "secondary")}`,
      );
      return;
    }
    go("/login");
    return;
  }
  if (path === "/admin/analytics" || path === "/admin/analytics/export") {
    if(!state.user.analytics_access){frame('<h1>Доступ не предоставлен</h1><p>Аналитика доступна владельцу платформы.</p>');return}
    const module=await import("./admin-analytics.js?v=20261015-compact-1");
    if(version===state.routeVersion)await module.mountAdmin(frame,{page:path.endsWith("/export")?"export":"analytics"});return;
  }
  if (path === "/app") {if(typeof trackPage==="function")trackPage(path);return setup()}
  if (path === "/history") {if(typeof trackPage==="function")trackPage(path);return history()}
  const match = path.match(/^\/practice\/([^/]+)$/);
  if (match) {
    frame('<div class="loading" role="status">Открываем тренировку…</div>');
    try {
      const p = await api.practice(decodeURIComponent(match[1]));
      if (version !== state.routeVersion) return;
      state.practice = p;
      if(typeof trackPage==="function")trackPage(path,p);
      await restorePending(p);
      if (version !== state.routeVersion || !state.user) return;
      forgetReturn();
      practicePage(p);
      if (queuedAnswers(p).length) {
        queuedAnswers(p).forEach((answer) => { answer.error = null; });
        void pumpAnswerUploads(p);
      }
      if (
        state.pending?.autoSave &&
        !state.pending.interrupted &&
        !state.pending.conflict
      )
        await saveRecording();
      else if (
        !state.pending &&
        !p.report &&
        !p.active_job &&
        p.segments.some((s) => s.kind === "speech") &&
        (!p.latest_job ||
          (p.latest_job.kind === "questions" &&
            p.latest_job.status === "succeeded" &&
            !nextSegment(p)))
      )
        await continueAfterSave(p);
    } catch (error) {
      if (
        error.status === 404 &&
        state.user &&
        version === state.routeVersion
      ) {
        const ownerId = state.user.id;
        const drafts = await loadRecordingDrafts(ownerId).catch(() => []);
        const draft = drafts.find(
          (d) => d.practiceId === decodeURIComponent(match[1]),
        );
        if (
          draft &&
          version === state.routeVersion &&
          state.user?.id === ownerId
        ) {
          state.practice = { id: draft.practiceId, config: draft.config };
          state.pending = {
            ...draft,
            url: URL.createObjectURL(draft.blob),
            missing: true,
          };
          state.pendingPersisted = true;
          showPending();
          return;
        }
      }
      if (version === state.routeVersion)
        frame(
          `<h1>Тренировка недоступна</h1>${errorBox(errorText(error))}<a href="#/history" class="button secondary">Открыть историю</a>`,
        );
    }
    return;
  }
  go("/landing");
}
async function submitForm(event) {
  const form = event.target;
  if (!form.matches("form")) return;
  event.preventDefault();
  const submit = form.querySelector("[type=submit]"),
    error = form.querySelector(".form-error");
  submit.disabled = true;
  const previousLabel = submit.textContent;
  submit.textContent =
    form.id === "auth-form"
      ? form.dataset.mode === "register"
        ? "Регистрация…"
        : form.dataset.mode === "reset"
          ? "Сохраняем пароль…"
          : "Входим…"
      : form.id === "setup-form"
        ? "Открываем запись…"
        : "Отправляем отзыв…";
  form.setAttribute("aria-busy", "true");
  error.textContent = "";
  const body = Object.fromEntries(new FormData(form));
  try {
    if (form.id === "auth-form") {
      const mode = form.dataset.mode;
      if(mode==="register"){telemetry("registration_submitted");if(typeof flush==="function")void flush()}
      if (mode === "reset") {
        await api.reset({ token: body.token.trim(), password: body.password });
        notify("Пароль обновлён. Войди с новым паролем.");
        go("/login");
        return;
      }
      const data =
        mode === "register"
          ? await api.register({
              ...body,
              email: body.email.trim(),
              name: body.name.trim(),
            })
          : await api.login({ ...body, email: body.email.trim() });
      state.user = data.user;
      if(typeof analyticsActor==="function")analyticsActor(state.user?.id);
      state.providerReady = data.provider_ready ?? state.providerReady;
      state.online = true;
      frame(`<div class="loading" role="status">${mode === "register" ? "Аккаунт создан. Открываем тренировку…" : "Вход выполнен. Открываем тренировку…"}</div>`);
      await resumeAfterLogin();
    } else if (form.id === "setup-form") {
      const minutes = Number(body.minutes);
      const seconds = Number(body.seconds);
      if (!body.minutes?.trim() || !body.seconds?.trim() ||
          !Number.isInteger(minutes) || !Number.isInteger(seconds) ||
          minutes < 0 || minutes > 10 || seconds < 0 || seconds > 59)
        throw new Error("Укажи минуты от 0 до 10 и секунды от 0 до 59 целыми числами");
      const totalSeconds = minutes * 60 + seconds;
      if (totalSeconds < 30 || totalSeconds > 600)
        throw new Error("Укажи время от 30 секунд до 10 минут");
      const config = {
        scenario: body.scenario,
        topic: body.topic.trim(),
        duration: totalSeconds / 60,
        questions: body.questions === "on",
        criteria: body.criteria?.trim() || "",
      };
      try {
        sessionStorage.setItem("practice-topic", config.topic);
      } catch {}
      if (!state.user) { go("/register"); return; }
      const p = await api.createPractice(config);
      go(`/practice/${encodeURIComponent(p.id)}`);
    } else if (form.id === "feedback-form") {
      await api.feedback(state.practice.id, {
        rating: Number(body.rating),
        text: body.text?.trim() || "",
      });
      form.innerHTML =
        "<h2>Спасибо за отзыв</h2><p>Он поможет доработать следующие разборы.</p>";
    }
  } catch (e) {
    if(form.id==="auth-form"&&form.dataset.mode==="register")telemetry("registration_failed",{error_code:e.code||"REGISTRATION_FAILED"});
    if (form.id === "auth-form" && state.user && !form.isConnected)
      frame(`<h1>Вход выполнен</h1>${errorBox(errorText(e))}${startLink("Открыть тренировку", "secondary")}`);
    else error.textContent = errorText(e);
  } finally {
    submit.disabled = false;
    submit.textContent = previousLabel;
    form.removeAttribute("aria-busy");
  }
}
async function action(event) {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  target.disabled = true;
  const name = target.dataset.action;
  if (!state.user && ["guest-starter", "guest-again", "start-record"].includes(name)) {
    target.disabled = false;
    go("/register");
    return;
  }
  try {
    switch (name) {
      case "landing-context": {
        const panel = document.getElementById("landing-context-copy");
        if (target.getAttribute("aria-pressed") === "true") break;
        document.querySelectorAll("[data-context]").forEach((choice) => choice.setAttribute("aria-pressed", String(choice === target)));
        panel.querySelectorAll("[data-context-copy]").forEach((copy) => copy.setAttribute("aria-hidden", String(copy.dataset.contextCopy !== target.dataset.context)));
        animateContextChange(panel);
        break;
      }
      case "history-page":
        await history(Number(target.dataset.offset));
        break;
      case "download-report":
        telemetry("report_export_requested",{report_version_id:state.practice.report_version_id},state.practice.id);
        downloadReport(state.practice);
        break;
      case "choose-focus":
        document
          .querySelector(".next-attempt")
          ?.scrollIntoView({ block: "start", behavior: "instant" });
        document
          .querySelector('input[name="repeat-focus"]:checked')
          ?.focus({ preventScroll: true });
        break;
      case "refresh":
        await navigate();
        break;
      case "reconnect":
        await initialize();
        break;
      case "logout":
        if (
          state.recording ||
          (state.pending && !state.pendingPersisted) ||
          state.uploading || queuedAnswers().length
        ) {
          notify("Сначала сохрани или отмени текущую запись.");
          return;
        }
        await api.logout();
        discardPending();
        state.user = null;
        if(typeof analyticsActor==="function")analyticsActor(null);
        state.practice = null;
        state.adminReturn=false;try{sessionStorage.removeItem("analytics-return")}catch{}
        forgetReturn();
        go("/landing");
        break;
      case "guest-starter": {
        state.guest = {
          id: "guest",
          config: {
            scenario: "speech",
            topic: "",
            duration: 1,
            questions: true,
            criteria: "",
          },
          segments: [],
          questions: [],
          report: null,
        };
        practicePage(state.guest, true);
        break;
      }
      case "guest-analyze":
        if (state.user) await importGuest();
        else go("/register");
        break;
      case "starter": {
        const p = await api.createPractice({
          scenario: "speech",
          topic: "",
          duration: 1,
          questions: true,
          criteria: "",
        });
        go(`/practice/${encodeURIComponent(p.id)}`);
        break;
      }
      case "new-topic": {
        if (!state.user.onboarding_completed) {
          const data = await api.completeOnboarding();
          state.user = data.user;
        }
        go("/app");
        break;
      }
      case "toggle-mic":
        await toggleMic();
        break;
      case "toggle-camera":
        await toggleCamera();
        break;
      case "check-mic":
        await checkMic();
        break;
      case "start-record":
        await beginMeeting();
        break;
      case "stop-record":
        stopRecording();
        break;
      case "save-record":
        await saveRecording();
        break;
      case "retry-answers":
        queuedAnswers().forEach((answer) => { answer.error = null; });
        updateAnswerProgress(state.practice);
        await pumpAnswerUploads(state.practice);
        break;
      case "reauth-answers":
        await state.answerPump;
        await Promise.all(queuedAnswers().map((answer) => answer.persistence));
        rememberReturn(state.practice.id, queuedAnswers()[0]?.ownerId);
        go("/login");
        break;
      case "discard-record":
        if (state.pending) await clearRecordingDraft(state.pending);
        discardPending();
        practicePage(state.practice, state.practice.id === "guest");
        break;
      case "reauth":
        await persistPending();
        rememberReturn(state.pending.practiceId, state.pending.ownerId);
        go("/login");
        break;
      case "use-server-recording": {
        if (
          !confirm(
            "Удалить эту запись и продолжить с ранее сохранённой?",
          )
        )
          return;
        const id = state.pending.practiceId;
        await clearRecordingDraft(state.pending);
        discardPending();
        go(`/practice/${encodeURIComponent(id)}`);
        break;
      }
      case "delete-local-draft":
        if (
          !confirm(
            "Удалить эту запись? Сначала скачай её, если хочешь оставить копию.",
          )
        )
          return;
        await clearRecordingDraft(state.pending);
        await clearDraft(state.pending.clientKey);
        discardPending();
        go("/app");
        break;
      case "questions":
      case "refresh-report":
      case "report": {
        if (queuedAnswers().length) return;
        target.disabled = true;
        const p = state.practice;
        const version = state.routeVersion;
        try {
          const job = await api.startJob(p.id, name === "refresh-report" ? "report" : name, {refresh: name === "refresh-report"});
          if (version === state.routeVersion && state.practice?.id === p.id)
            processingPage(p, job);
        } catch (error) {
          if (version === state.routeVersion && state.practice?.id === p.id)
            throw error;
        }
        break;
      }
      case "delete": {
        if (
          !confirm(
            "Удалить тренировку, запись и разбор? Восстановить их из интерфейса не получится.",
          )
        )
          return;
        target.disabled = true;
        await api.deletePractice(target.dataset.id);
        const drafts = await loadRecordingDrafts(state.user.id);
        await Promise.all(
          drafts
            .filter((d) => d.practiceId === target.dataset.id)
            .map(clearRecordingDraft),
        );
        notify("Тренировка удалена.");
        await history();
        break;
      }
      case "repeat-selected":
      case "repeat": {
        const selected = document.querySelector('input[name="repeat-focus"]:checked')?.value;
        if (name === "repeat-selected" && selected === undefined) {
          notify("Выбери рекомендацию для повторной попытки.");
          break;
        }
        const recommendation = selected === undefined ? null : repeatChoices(state.practice.report)[Number(selected)];
        if (!state.user.onboarding_completed) {
          const data = await api.completeOnboarding();
          state.user = data.user;
        }
        const p = await api.createPractice({
          ...state.practice.config,
          repeat_source_id: state.practice.id,
          repeat_recommendation_index: recommendation?.recommendationIndex ?? null,
        });
        go(`/practice/${encodeURIComponent(p.id)}`);
        break;
      }
      case "guest-again":
        await clearDraft().catch(() => {});
        state.guest?.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
        state.guest = null;
        state.guestPersisted = false;
        setup(true);
        break;
    }
  } catch (error) {
    notify(errorText(error));
    target.disabled = false;
  } finally {
    if (target.isConnected) {
      if (name === "toggle-camera") updateCameraUI();
      else target.disabled = false;
    }
  }
}
async function initialize() {
  frame('<div class="loading" role="status">Открываем сцену…</div>');
  try {
    state.adminReturn=sessionStorage.getItem("analytics-return")==="1";
    const saved = JSON.parse(sessionStorage.getItem("practice-return"));
    if (/^[a-f0-9]{32}$/.test(saved?.practiceId)) state.authReturn = saved;
  } catch {}
  try {
    const draft = await loadDraft();
    if (draft) {
      state.guest = guestFromDraft(draft);
      state.guestPersisted = true;
    }
  } catch {
    state.guestPersisted = false;
  }
  try {
    const me = await api.me();
    state.user = me.user;
    if(typeof analyticsActor==="function")analyticsActor(state.user?.id);
    state.providerReady = me.provider_ready;
    state.online = true;
    if (state.pending && state.pending.ownerId !== state.user?.id)
      discardPending();
  } catch {
    state.online = false;
  }
  if (state.guest?.ownerId && state.guest.ownerId !== state.user?.id) {
    state.guest.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
    state.guest = null;
    state.guestPersisted = false;
  }
  await navigate();
}
function guestFromDraft(draft) {
  state.guestPersisted = true;
  return {
    ...draft,
    id: "guest",
    segments: [
      { kind: "speech", index: 0, media_url: URL.createObjectURL(draft.blob) },
    ],
    questions: [],
    report: null,
  };
}
app.addEventListener("submit", submitForm);
app.addEventListener("click", action);
document.querySelector(".skip-link").addEventListener("click", (event) => {
  event.preventDefault();
  document.querySelector("#main")?.focus();
});
window.addEventListener("hashchange", () => void navigate());
window.addEventListener("beforeunload", (event) => {
  if (
    state.recording ||
    (state.pending && !state.pendingPersisted) ||
    state.uploading ||
    state.answerQueue.some((answer) => !answer.persisted) ||
    (state.guest?.blob && !state.guestPersisted)
  ) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("session-expired", sessionExpired);
document.addEventListener("play",(event)=>{
  if(!document.querySelector(".report-reading")||!state.practice)return;
  const segment=(state.practice.segments||[]).find(s=>s.media_url===event.target.getAttribute?.("src"));
  if(segment)telemetry("media_play_started",{segment_id:segment.id},state.practice.id);
},true);
document.addEventListener("click",(event)=>{
  const link=event.target.closest?.(".media-list a[download]");
  if(!link||!document.querySelector(".report-reading")||!state.practice)return;
  const segment=(state.practice.segments||[]).find(s=>link.getAttribute("href")===s.media_url+"?download=true");
  if(segment)telemetry("media_download_requested",{segment_id:segment.id},state.practice.id);
});

installTypography([app, document.querySelector("#toast")]);
void initialize();
