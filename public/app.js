import { installTypography } from "./typography.js?v=20261013-type";
import { mountLandingMotion, animateContextChange } from "./landing-motion.js?v=20261013-refine";
import { api } from "./api.js?v=20261013-auth-gate";
import { LiveAudioCapture } from "./live-audio.js?v=20261011-live";
import {
  saveDraft,
  loadDraft,
  clearDraft,
  saveRecordingDraft,
  loadRecordingDrafts,
  clearRecordingDraft,
} from "./guest-draft.js?v=20261013-auth-gate";
const app = document.querySelector("#app");
let landingCleanup = () => {};
const state = {
  user: null,
  providerReady: false,
  inviteRequired: false,
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
  activeAnswer: null,
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
  return error?.message || "Не удалось выполнить действие. Попробуй ещё раз.";
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
function header() {
  return `<header class="header"><a class="home-link" href="#/landing">Главная</a><nav class="primary-nav" aria-label="Основная навигация">${state.user ? `<a href="#/app">Тренировка</a><a href="#/history">История</a>` : `<a href="#/login">Вход</a><a class="registration-link" href="#/register">Регистрация</a>`}</nav>${state.user ? `<div class="account-actions">${button("Выход", "logout", "text")}</div>` : ""}</header>`;
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
        <p class="landing-kicker" data-enter>Сцена без страха · Репетиция выступлений</p>
        <h1 id="landing-title" data-enter>Отрепетируй речь до встречи с аудиторией</h1>
        <p class="landing-lead" data-enter>Запиши выступление, ответь на вопросы по сказанному и выбери, что улучшить в следующей попытке.</p>
        <p class="landing-start-note" data-enter>${state.user ? "Твоя следующая попытка останется в истории тренировок." : `Зарегистрируйся или войди, чтобы записать выступление и получить разбор.${state.inviteRequired ? " Для регистрации нужен код приглашения от организатора." : ""}`}</p>
        <div class="landing-hero-actions" data-enter>${startLink("Начать с минуты речи", "primary landing-cta")}</div>
      </div>
    </section>
    <section class="landing-contexts landing-light" id="landing-contexts" aria-labelledby="contexts-title">
      <div class="landing-section-heading" data-reveal><p class="landing-kicker">Под твою задачу</p><h2 id="contexts-title">Когда важно объяснить свою мысль</h2><p>Выбери ситуацию и посмотри, на чём можно сосредоточиться в тренировке.</p></div>
      <div class="landing-context-grid" role="group" aria-label="Ситуация для тренировки" data-reveal>
        ${[
          ["speech", "Выступление", "Главная мысль и понятные аргументы"],
          ["defense", "Защита проекта", "Идея, решение и вопросы к ним"],
          ["free", "Свободная речь", "Тема, которую хочется обсудить"],
        ].map(([key, title, copy], index) => `<button class="landing-context-card" type="button" data-action="landing-context" data-context="${key}" aria-pressed="${index === 0}" aria-controls="landing-context-panel"><span class="landing-context-mark" aria-hidden="true">${landingContextIcon(key)}</span><strong>${title}</strong><span>${copy}</span><span class="context-selected" aria-hidden="true">Выбрано</span></button>`).join("")}
      </div>
      <div class="landing-context-panel" id="landing-context-panel"><div class="landing-context-copy" id="landing-context-copy" aria-live="polite">${["speech", "defense", "free"].map((key) => `<div data-context-copy="${key}" aria-hidden="${key !== "speech"}">${landingContextCopy(key)}</div>`).join("")}</div>${startLink("Начать с минуты речи", "secondary")}</div>
    </section>
    <section class="landing-meeting landing-light" aria-labelledby="meeting-title">
      <figure class="landing-meeting-visual" data-reveal><div class="landing-meeting-frame"><div class="landing-meeting-caption"><span>Пространство для репетиции</span><span>Твоё выступление</span></div><img src="/audience-meeting-v1.png" width="1536" height="1024" alt="Иллюстрация виртуальной аудитории в переговорной" loading="lazy"><div class="landing-meeting-tools" aria-hidden="true">${deviceIcon("mic")}${deviceIcon("camera")}</div></div></figure>
      <div class="landing-feature-copy" data-reveal><p class="landing-kicker">Знакомая обстановка</p><h2 id="meeting-title">Говори так, как будешь говорить на встрече</h2><p>Микрофон, камера по желанию и слушатели перед тобой. После выступления вопросы появляются в чате этой же встречи.</p><ul class="landing-feature-list"><li><strong>Запись сохраняется</strong><span>После завершения выступления можно вернуться к своей попытке.</span></li><li><strong>Вопросы по твоим словам</strong><span>Их основа — подтверждённая расшифровка сохранённой речи.</span></li><li><strong>Один фокус для повторения</strong><span>В разборе выбираешь рекомендацию для следующей тренировки.</span></li></ul></div>
    </section>
    <section class="landing-method" aria-labelledby="method-title">
      <div class="landing-section-heading" data-reveal><p class="landing-kicker">Путь тренировки</p><h2 id="method-title">От первой минуты к следующей попытке</h2></div>
      <ol class="landing-process">
        <li data-reveal><span class="landing-step">1</span><h3>Запиши выступление</h3><p>Начни с минуты речи. Для своей задачи можно выбрать тему, сценарий и продолжительность.</p></li>
        <li data-reveal><span class="landing-step">2</span><h3>Ответь на вопросы</h3><p>Три вопроса по содержанию появятся в чате. Запиши ответы и получи разбор речи с цитатами.</p></li>
        <li data-reveal><span class="landing-step">3</span><h3>Попробуй ещё раз</h3><p>Выбери одну рекомендацию. Тема и фокус перейдут в новую тренировку.</p></li>
      </ol>
      <div class="landing-method-action" data-reveal>${startLink("Начать тренировку", "primary landing-cta")}</div>
    </section>
    <section class="landing-faq landing-light" aria-labelledby="faq-title">
      <div class="landing-faq-heading" data-reveal><p class="landing-kicker">Перед важным выступлением</p><h2 id="faq-title">Как репетиция поможет тебе подготовиться</h2><p>О том, что попробовать до выступления и как использовать обратную связь.</p></div>
      <div class="landing-faq-list" data-reveal>
        <details><summary>До выступления мало времени. С чего начать?</summary><div><p>Начни с короткой репетиции любого фрагмента своего выступления. После вопросов и разбора выбери одну рекомендацию для следующей попытки — например, уточнить вывод. Так у тебя будет понятная задача для оставшегося времени вместо попытки переделать всё выступление сразу.</p></div></details>
        <details><summary>Я знаю тему, но говорю сумбурно. Как это исправить?</summary><div><p>Запиши объяснение своими словами. При желании укажи, на что обратить внимание в разборе. Разбор даст замечания по содержанию и рекомендации с фрагментами твоей речи. Их можно использовать, чтобы перестроить объяснение, добавить недостающий пример и попробовать рассказать ещё раз.</p></div></details>
        <details><summary>Боюсь растеряться на вопросах. Как их отрепетировать?</summary><div><p>После выступления нейросеть задаст три вопроса по тому, что ты рассказал. Ты сможешь проговорить ответы и получить разбор вместе с основной речью. Это возможность заранее потренироваться объяснять свою мысль и подкреплять её аргументами. Вопросы реальной аудитории могут отличаться.</p></div></details>
        <details><summary>Что я пойму о своей речи после первой попытки?</summary><div><p>Увидишь, что в объяснении уже получается и что стоит изменить в следующей попытке. Например, рекомендация может касаться общего аргумента, которому не хватает примера. Замечания сопровождаются фрагментами твоей речи, поэтому их можно сопоставить с записью и решить, что именно доработать.</p></div></details>
        <details><summary>Чем это полезнее репетиции перед зеркалом?</summary><div><p>Перед зеркалом можно проговорить текст и посмотреть на себя. Здесь ты ещё получишь вопросы по своей речи и рекомендации по её содержанию. Это дополнительная обратная связь для проверки объяснения, когда ты уже привык к собственному тексту и не знаешь, что в нём изменить.</p></div></details>
        <details><summary>Я стесняюсь выступать. Здесь меня кто-то слушает?</summary><div><p>К тренировке не подключаются живые слушатели: перед тобой виртуальная аудитория, а вопросы задаёт нейросеть. Можно начать только с микрофоном и включить камеру по желанию. Ты можешь пробовать разные формулировки до того, как произнесёшь их на защите или встрече.</p></div></details>
        <details><summary>Как понять, что следующая попытка стала лучше?</summary><div><p>Выбери одну рекомендацию и проверь конкретное изменение. Если решишь добавить пример, сравни, легче ли теперь понять твой аргумент. Если уточнишь вывод, проверь, ясно ли, какую мысль должен запомнить слушатель. Записи и разборы сохраняются в истории, чтобы ты мог вернуться к предыдущей попытке.</p></div></details>
      </div>
    </section>
    <section class="landing-final" aria-labelledby="final-title"><div data-reveal><p class="landing-kicker">Перед важным днём есть время попробовать</p><h2 id="final-title">Начни с одной минуты своей речи</h2><p>Первое упражнение уже подготовлено. Можно закончить раньше или настроить тренировку под себя.</p>${startLink("Начать тренировку", "primary landing-cta")}</div></section>`,
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
    `<div class="auth-layout"><div class="auth-intro"><p class="eyebrow">${reset ? "Восстановление доступа" : "Репетиция начинается здесь"}</p><h1>${reset ? "Вернись к своим тренировкам" : state.guest?.blob && !reset ? "Получи разбор своего выступления" : register ? "Подготовься к своему выступлению" : "Продолжи свою тренировку"}</h1><p>${reset ? "Организатор выдаёт одноразовый код после проверки владельца аккаунта." : register ? (state.guest?.blob ? "Твоя запись уже готова. После регистрации перенесём её в аккаунт и подготовим разбор. Повторять выступление не нужно." : "После регистрации начни с короткого упражнения: запиши минуту речи и получи первый разбор.") : state.guest?.blob ? "Войди, чтобы получить разбор уже записанного выступления. Запись перейдёт в твой аккаунт." : state.authReturn ? "После входа вернёмся к незавершённой тренировке. Сохранённые записи повторять не нужно." : "Твои записи и разборы останутся в истории."}</p></div><section class="auth-panel"><h2>${reset ? "Новый пароль" : register ? "Регистрация" : "Войди в аккаунт"}</h2><form id="auth-form" data-mode="${mode}">${register ? '<label>Имя<input name="name" autocomplete="given-name" maxlength="80" required></label>' : ""}${reset ? '<label>Одноразовый код<input name="token" autocomplete="off" required></label>' : '<label>Электронная почта<input type="email" name="email" autocomplete="email" maxlength="254" required></label>'}<div class="field-group"><label>${reset ? "Новый пароль" : "Пароль"}<input type="password" name="password" autocomplete="${register || reset ? "new-password" : "current-password"}" ${register || reset ? 'minlength="10"' : ""} maxlength="128" required></label>${register || reset ? '<p class="field-hint">Не менее 10 символов.</p>' : ""}</div>${register ? `<label>Для чего тренируешься?<select name="role"><option value="student">Учёба и защита проекта</option><option value="professional">Работа и выступления</option><option value="other">Другое</option></select></label>${state.inviteRequired ? '<label>Код приглашения<input name="invite_code" autocomplete="off" required></label>' : ""}` : ""}<div class="form-error" role="alert"></div><button class="button primary" type="submit">${reset ? "Сохранить пароль" : register ? "Регистрация" : "Войти"}</button></form><p class="auth-links">${reset ? '<a href="#/login">Вернуться ко входу</a>' : register ? 'Уже есть аккаунт? <a href="#/login">Войти</a>' : '<a href="#/register">Регистрация</a> · <a href="#/reset">Восстановить доступ</a>'}</p></section></div>`,
  );
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
  if (
    state.pending?.ownerId !== state.user.id ||
    state.pending?.practiceId !== p.id
  ) {
    discardPending();
    const drafts = await loadRecordingDrafts(ownerId).catch(() => []);
    if (state.user?.id !== ownerId || state.practice?.id !== p.id) return;
    const boundGuest = state.guest;
    const accountDraft = drafts.find((d) => d.practiceId === p.id);
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
      state.pending = { ...draft, url: URL.createObjectURL(draft.blob) };
      state.pendingPersisted = !!accountDraft || state.guestPersisted;
    }
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
  else go("/app");
}

function sessionExpired() {
  const ownerId =
    state.user?.id || state.pending?.ownerId || state.recordingOwnerId;
  if (state.practice?.id && state.practice.id !== "guest")
    rememberReturn(state.practice.id, ownerId);
  state.user = null;
  state.liveCapture?.cancel();
  state.liveCapture = null;
  clearTimeout(state.poll);
  if (state.recording) {
    notify(
      "Сессия завершилась. Закончи запись — сохраним её в браузере и предложим войти.",
    );
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
    `<div class="page-heading"><p class="eyebrow">Твоя первая попытка</p><h1>Запись готова к разбору</h1><p class="page-description">${state.user ? "Перенесём выступление в твой аккаунт и подготовим разбор нейросети." : "Создай аккаунт, чтобы получить полный разбор этого выступления. Запись уже готова, повторять её не нужно."}</p></div><div class="guest-result-layout"><section class="guest-recording"><p class="eyebrow">Тема выступления</p><h2>${heading(p.config.topic || "Твоя речь")}</h2><p class="caption">Записано ${time(Math.round(p.durationSeconds || 0))}</p>${playback(p.segments[0].media_url, p.blob.type.startsWith("video/"))}<a class="quiet-link" href="${escape(p.segments[0].media_url)}" download="моя-запись">Скачать копию записи</a><p class="field-hint">${state.guestPersisted ? "Запись сохранена в этом браузере. В течение суток можно продолжить даже после обновления страницы." : "Браузер не разрешил сохранить черновик. Не обновляй и не закрывай вкладку до получения разбора."}</p></section><section class="guest-unlock"><h2>Что будет в полном разборе</h2><ul><li>Главная мысль и структура выступления</li><li>Что уже получается — с цитатами из твоей речи</li><li>Конкретная рекомендация для повторной попытки</li></ul><p>${p.config.questions ? "После входа в чате появятся три вопроса по выступлению. Запиши ответы, чтобы получить полный разбор речи и ответов." : "Разбор опирается на расшифровку твоей записи."} Затем можно повторить тренировку с выбранным фокусом.</p>${message ? errorBox(message) : ""}<div class="actions">${button(state.user ? "Получить разбор" : "Регистрация", "guest-analyze")}${!state.user ? '<a class="quiet-link" href="#/login">Уже есть аккаунт? Войти</a>' : ""}${button("Записать заново", "guest-again", "secondary")}</div></section></div>`,
  );
}
async function importGuest() {
  const draft = state.guest;
  if (!draft?.blob || state.uploading) return;
  state.uploading = true;
  frame(
    '<div class="processing"><p class="eyebrow">Продолжаем твою тренировку</p><h1>Сохраняем выступление в аккаунт</h1><p role="status">Запись уже готова. Не закрывай страницу во время загрузки.</p></div>',
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
        "В тренировке уже есть другая запись. Скачай исходный черновик перед продолжением.",
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
      `Аккаунт готов, но продолжить пока не удалось. ${errorText(error)} Исходная запись остаётся в браузере. Попробуй продолжить тренировку ещё раз.`,
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
  return `<form id="setup-form" data-guest="${guest}" class="setup-form"><h2>${guest ? "Твоя пробная запись" : "Настроить тренировку"}</h2><fieldset><legend>Сценарий</legend><div class="scenario-options"><label><input type="radio" name="scenario" value="speech" checked><span><strong>Выступление</strong><small>Речь для аудитории</small></span></label><label><input type="radio" name="scenario" value="defense"><span><strong>Защита проекта</strong><small>Идея и аргументы</small></span></label><label><input type="radio" name="scenario" value="free"><span><strong>Свободная речь</strong><small>Тема на твой выбор</small></span></label></div></fieldset><label><span class="label-title">Тема выступления <span class="optional">необязательно</span></span><input name="topic" maxlength="300" placeholder="Название для истории тренировок" value="${escape(savedTopic())}"></label><label>Продолжительность<select name="duration"><option value="1">1 минута</option><option value="3">3 минуты</option><option value="5" selected>5 минут</option><option value="10">10 минут</option></select></label><div class="field-group"><label class="check"><input type="checkbox" name="questions" checked aria-describedby="questions-hint"><span>После выступления ответить на три вопроса аудитории</span></label><p class="field-hint" id="questions-hint">До 10 минут аудио на тренировку. С вопросами: выступление до 7 минут и три ответа до минуты каждый.</p></div><label><span class="label-title">На что обратить внимание <span class="optional">необязательно</span></span><textarea name="criteria" maxlength="2000" rows="3" placeholder="Например, понятны ли аргументы и вывод"></textarea></label><div class="form-error" role="alert"></div><button type="submit" class="button primary">Перейти к записи</button></form>`;
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
        continuation = `<section class="narrow"><h2>Продолжи незавершённую тренировку</h2><div class="history-list">${items
          .slice(0, 3)
          .map(
            (p) =>
              `<article class="history-item"><div><h3>${heading(p.config.topic || "Тренировка")}</h3><p class="caption">${drafts.some((d) => d.practiceId === p.id) ? "В браузере есть запись для сохранения" : p.status === "processing" ? "Обработка продолжается" : p.status === "failed" ? "Запись сохранена. Обработку можно повторить" : "Можно вернуться к следующему этапу"}</p></div><a class="button secondary" href="#/practice/${encodeURIComponent(p.id)}">Продолжить</a></article>`,
          )
          .join(
            "",
          )}</div><a class="quiet-link" href="#/history">Все тренировки</a></section>`;
    } catch {
      if (version !== state.routeVersion || !state.user) return;
      continuation = `<div class="notice">Не удалось проверить незавершённые тренировки. <a href="#/history">Открыть историю</a></div>`;
    }
  }
  const first = guest || !state.user.onboarding_completed;
  frame(
    `<div class="page-heading"><p class="eyebrow">${guest ? "Тренировка без регистрации" : first ? "Первая тренировка" : "Рабочее пространство"}</p><h1>${first ? "Начни с короткого выступления" : "Что будем репетировать?"}</h1>${first ? '<p class="page-description">Запиши речь на любую тему, ответь на вопросы в чате и получи разбор по сказанному.</p>' : ""}</div>${guest ? `<div class="notice">${state.user ? "Сначала запиши выступление. Затем перенесём запись в твой аккаунт и продолжим тренировку с вопросами и разбором." : "Сначала запиши выступление. После записи создай аккаунт, чтобы получить полный разбор этой попытки. Записывать заново не понадобится."}</div>` : !state.providerReady ? '<div class="notice">Сервис нейросети ещё не настроен. Можно сохранить запись; разбор станет доступен после подключения сервиса.</div>' : ""}${continuation}<div class="setup-layout">${first ? `<aside class="starter"><span class="tag">Речь до 1 минуты</span><h2>Запиши свою речь</h2><p>Тему и содержание выбираешь ты. Разбор будет опираться на то, что ты скажешь.</p>${button("Записать первую минуту", guest ? "guest-starter" : "starter")}<p class="caption">После речи в чате появятся три вопроса. Запиши ответы, чтобы получить полный разбор.</p></aside><section class="first-guide"><h2>Как пройти первую тренировку</h2><ol><li><strong>Запиши речь</strong><p>Говори на свою тему. Можно закончить раньше минуты.</p></li><li><strong>Ответь на вопросы и получи разбор</strong><p>${guest ? "После записи создай аккаунт. Сохраним выступление, зададим три вопроса по его содержанию и разберём речь вместе с ответами." : "После сохранения выступления в чате появятся три вопроса. Запиши ответы, и нейросеть подготовит разбор."}</p></li><li><strong>Повтори с одной рекомендацией</strong><p>Выбери в разборе, что хочешь улучшить. Тема и выбранный фокус перейдут в новую попытку.</p></li></ol><details class="custom-setup"><summary>Настроить свою тренировку</summary>${setupForm(guest)}</details></section>` : `<aside class="starter"><p class="eyebrow">Один фокус на попытку</p><h2>Отрепетируй свою речь</h2><p>${guest ? "Запиши выступление на свою тему и прослушай его." : "Запиши выступление и получи обратную связь по своей речи. После разбора можно выбрать рекомендацию для следующей попытки."}</p></aside>${setupForm(guest)}`}</div>`,
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
function repeatChoices(report) {
  return [
    { title: "Главное в этой попытке", text: report.insight },
    ...(report.recommendations || []),
  ].filter(
    (item, index, all) =>
      item.text &&
      !all.slice(0, index).some((previous) => previous.text === item.text),
  );
}
function repeatPanel(p) {
  const recommendations = repeatChoices(p.report);
  return `<section class="next-attempt"><div><h2>Примени рекомендацию в новой попытке</h2><p>Выбери, что хочешь улучшить. Сохраним тему, продолжительность и выбранный фокус.</p>${recommendations.length ? `<fieldset><legend>Фокус следующей попытки</legend><div class="focus-options">${recommendations.map((item, index) => `<label class="focus-option"><input type="radio" name="repeat-focus" value="${index}"${index === 0 ? " checked" : ""}><span><strong>${heading(item.title)}</strong><span class="focus-description">${escape(item.text)}</span></span></label>`).join("")}</div></fieldset>` : ""}<div class="actions">${button("Записать повторную попытку", "repeat")}${button("Выбрать другую тему", "new-topic", "secondary")}</div></div></section>`;
}
async function history(offset = 0) {
  frame(
    '<p class="eyebrow">Твои тренировки</p><h1>История</h1><div class="loading" role="status">Загружаем записи…</div>',
  );
  const version = state.routeVersion;
  try {
    const data = await api.practices(offset);
    if (version !== state.routeVersion) return;
    frame(
      `<div class="page-heading row"><div><p class="eyebrow">Твои тренировки</p><h1>История</h1></div><a class="button primary" href="#/app">Новая тренировка</a></div>${data.items.length ? `<div class="history-list">${data.items.map((p) => `<article class="history-item"><div><p class="caption">${escape(date(p.created_at))}</p><h2><a href="#/practice/${encodeURIComponent(p.id)}">${heading(p.config?.topic || "Тренировка")}</a></h2><span class="tag ${p.status === "ready" ? "green" : ""}">${{ draft: "Запись и подготовка", processing: "Обрабатывается", ready: "Разбор готов", failed: "Нужна повторная обработка" }[p.status] || escape(p.status)}</span></div><div class="actions"><a class="button secondary" href="#/practice/${encodeURIComponent(p.id)}">${p.status === "ready" ? "Посмотреть разбор" : "Продолжить"}</a>${button("Удалить", "delete", "text", `data-id="${escape(p.id)}"`)}</div></article>`).join("")}</div>${`<div class="actions">${offset > 0 ? button("Предыдущие", "history-page", "secondary", `data-offset="${Math.max(0, offset - 30)}"`) : ""}${offset + data.items.length < data.total ? button("Следующие", "history-page", "secondary", `data-offset="${offset + 30}"`) : ""}</div>`}` : `<div class="empty"><h2>Здесь появится твоя первая попытка</h2><p>Запиши выступление. Сохранённая запись и разбор останутся в истории.</p><a class="button primary" href="#/app">Начать тренировку</a></div>`}`,
    );
  } catch (error) {
    if (version === state.routeVersion)
      frame(
        `<h1>История</h1>${errorBox(errorText(error))}${button("Попробовать ещё раз", "refresh", "secondary")}`,
      );
  }
}
function reportMarkup(report) {
  return `<section class="report-insight"><h2>Главное в этой попытке</h2><p class="insight-copy">${escape(report.insight)}</p></section><div class="report-columns"><section><h2>Уже получается</h2>${(report.strengths || []).map((item) => reportItem(item, "strength")).join("") || "<p>Для вывода не хватило данных.</p>"}</section><section><h2>Что попробовать в следующей попытке</h2>${(report.recommendations || []).map((item) => reportItem(item, "recommendation")).join("") || "<p>Конкретных рекомендаций пока нет.</p>"}</section></div>${report.metrics?.length ? `<section class="report-metrics"><h2>Наблюдения</h2>${report.metrics.map((m) => `<article><span class="eyebrow">${escape(m.label)}</span><h3>${heading(m.title)}</h3><p>${escape(m.text)}</p></article>`).join("")}</section>` : ""}${report.criteria?.length ? `<section class="report-section"><h2>Выбранные критерии</h2>${report.criteria.map((c) => `<article class="criterion"><strong>${escape(c.criterion)}</strong><span class="tag">${{ met: "Есть в речи", partial: "Частично", not_met: "Не найдено", unknown: "Недостаточно данных" }[c.status] || "Недостаточно данных"}</span><p>${escape(c.evidence)}</p></article>`).join("")}</section>` : ""}${report.limitations?.length ? `<div class="notice"><strong>Границы разбора</strong><ul>${report.limitations.map((l) => `<li>${escape(l)}</li>`).join("")}</ul></div>` : ""}<details class="transcript"><summary>Расшифровка речи</summary><p>${escape(report.transcript)}</p></details>`;
}
function downloadReport(p) {
  const report = p.report;
  const sections = [
    "Сцена без страха",
    p.config.topic,
    date(p.created_at),
    "",
    report.insight,
  ];
  for (const [label, items] of [
    ["Уже получается", report.strengths],
    ["Что попробовать", report.recommendations],
    ["Наблюдения", report.metrics],
  ]) {
    sections.push("", label);
    for (const item of items || [])
      sections.push(
        item.title,
        item.text,
        item.evidence ? `Фрагмент речи: ${item.evidence}` : "",
      );
  }
  sections.push(
    "",
    "Границы разбора",
    ...(report.limitations || []),
    "",
    "Расшифровка",
    report.transcript || "",
  );
  const url = URL.createObjectURL(
    new Blob([sections.join("\n")], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "разбор-выступления.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function reportItem(item, cls) {
  return `<article class="report-item ${cls}"><h3>${heading(item.title)}</h3>${item.evidence ? `<blockquote>${escape(item.evidence)}</blockquote>` : ""}<p>${escape(item.text)}</p></article>`;
}
function reportPage(p) {
  if (!state.user) {
    go("/login");
    return;
  }
  frame(
    `${practiceProgress(p, "report")}<div class="page-heading"><p class="eyebrow">Разбор · ${escape(date(p.created_at))}</p><h1>${heading(p.config.topic || "Твоя тренировка")}</h1></div><p class="page-description">Прочитай наблюдения и рекомендации, затем выбери один фокус для повторной попытки.</p><div class="actions report-actions">${button("Выбрать фокус следующей попытки", "choose-focus")}${button("Скачать разбор", "download-report", "secondary")}</div>${reportMarkup(p.report)}<section class="report-section"><h2>Твои записи</h2>${mediaMarkup(p)}</section>${repeatPanel(p)}<form id="feedback-form" class="feedback-form"><h2>Был ли разбор полезен?</h2><fieldset><legend>Оценка от 1 до 5</legend><div class="ratings">${[1, 2, 3, 4, 5].map((n) => `<label><input type="radio" name="rating" value="${n}" required><span>${n}</span></label>`).join("")}</div></fieldset><label><span class="label-title">Что стоит улучшить? <span class="optional">необязательно</span></span><textarea name="text" rows="3" maxlength="2000"></textarea></label><div class="form-error" role="alert"></div><button type="submit" class="button secondary">Отправить отзыв</button></form>`,
  );
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
    600 -
      (p.segments || []).reduce(
        (sum, s) => sum + Number(s.duration_seconds || 0),
        0,
      ),
  );
  return segment.kind === "answer"
    ? Math.min(60, Math.floor(remaining))
    : Math.min(Number(p.config.duration) * 60, p.config.questions ? 420 : 600);
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
  const messages = (p.questions || [])
    .map((question, i) => {
      const answer = p.segments.find(
        (s) => s.kind === "answer" && Number(s.index) === i + 1,
      );
      return `<li class="chat-message${segment?.index === i + 1 ? " is-current" : ""}" style="--message-delay:${i * 60}ms"><span class="chat-author">${["Мария", "Алексей", "Ирина"][i] || "Участник"}</span><p>${escape(question)}</p>${answer ? `<div class="chat-reply"><span class="chat-answer-state">Ты · Ответ сохранён</span>${playback(answer.media_url, answer.has_video)}</div>` : ""}</li>`;
    })
    .join("");
  const failed =
    (p.latest_job?.status === "failed" || p.status === "failed") &&
    !p.questions?.length;
  if (state.pending?.kind === "speech" && state.pending.practiceId === p.id) {
    const pending = state.pending;
    return `<aside class="meeting-chat" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header><div class="chat-next"><p role="status">${state.uploading ? "Сохраняем выступление…" : pending.interrupted ? "Запись прервалась. Восстановили сохранённый фрагмент — прослушай его перед продолжением." : "Выступление записано. Осталось сохранить его в аккаунт."}</p>${!state.uploading ? `<p>${pendingPersistenceText()}</p>${pending.interrupted ? playback(pending.url, pending.blob.type.startsWith("video/")) : ""}${!state.user && pending.ownerId ? button("Войти и продолжить", "reauth") : `${button(pending.interrupted ? "Сохранить фрагмент и продолжить" : "Повторить сохранение", "save-record")}${button("Перезаписать", "discard-record", "secondary")}`}<a href="${escape(pending.url)}" download="моя-запись">Скачать копию записи</a>` : ""}</div></aside>`;
  }
  if (p.id === "guest" && p.blob) {
    return `<aside class="meeting-chat" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header><div class="chat-next"><p role="status">${p.interrupted ? "Запись прервалась. Восстановили сохранённый фрагмент." : `Выступление сохранено${state.guestPersisted ? " в браузере" : " в этой вкладке"}.`}</p>${p.interrupted ? playback(p.segments[0].media_url, p.blob.type.startsWith("video/")) : ""}<p>${state.user ? "Продолжи в своём аккаунте, чтобы получить вопросы и полный разбор." : "Создай аккаунт, чтобы получить вопросы по этой речи и полный разбор. Записывать заново не нужно."}</p>${state.guestNotice ? errorBox(state.guestNotice) : ""}${button(state.user ? "Продолжить тренировку" : "Регистрация", "guest-analyze")}${!state.user ? '<a href="#/login">Уже есть аккаунт? Войти</a>' : ""}${button("Перезаписать", "guest-again", "secondary")}<a href="${escape(p.segments[0].media_url)}" download="моя-запись">Скачать копию записи</a>${!state.guestPersisted ? "<p>Не закрывай и не обновляй вкладку: браузер не разрешил сохранить черновик.</p>" : ""}</div></aside>`;
  }
  return `<aside class="meeting-chat${arrival ? " chat-arrival" : ""}" aria-label="Вопросы по выступлению"><header><h2>Чат</h2></header><ol class="chat-messages" role="log" aria-label="Чат встречи" aria-live="polite" aria-relevant="additions">${messages}</ol><div class="chat-next">${job ? `<p id="job-status" role="status">${jobStage(job.stage)}</p><p class="caption">Вопросы появятся здесь, когда будут готовы.</p><div id="poll-error" role="alert"></div>` : !p.questions?.length ? `<p>${state.providerReady ? "Выступление сохранено. Осталось подготовить вопросы." : "Сервис нейросети недоступен. Выступление сохранено."}</p>${failed ? errorBox(p.latest_job?.error?.message || "Не удалось подготовить вопросы. Можно попробовать ещё раз.") : ""}${button("Подготовить вопросы", "questions", "primary", state.providerReady ? "" : "disabled")}` : segment && state.activeAnswer !== `${p.id}:${segment.index}` ? `<p>Вопрос ${segment.index} из ${p.questions.length}</p>${button("Ответить на вопрос", "open-answer")}` : `<p>Ответ на вопрос ${segment?.index} из ${p.questions.length}</p>`}</div></aside>`;
}
function meetingPage(p, guest = false, job = null) {
  const pendingSpeech =
    state.pending?.kind === "speech" && state.pending.practiceId === p.id;
  const segment = pendingSpeech ? null : nextSegment(p);
  const chat = !!(
    job ||
    pendingSpeech ||
    (p.config.questions && p.segments?.some((s) => s.kind === "speech"))
  );
  const devicesAvailable = true;
  const canRecord =
    !!segment &&
    !job &&
    (segment.kind === "speech" ||
      state.activeAnswer === `${p.id}:${segment.index}`);
  const content = `<div class="meeting-topbar"><a class="quiet-link" href="#${guest ? "/guest" : "/app"}">К тренировке</a><h1>${heading(p.config.topic || "Твоя речь")}</h1>${canRecord ? `<span class="meeting-time" id="record-timer" aria-label="Осталось времени">${time(recordingLimit(p, segment))}</span>` : '<span class="meeting-time">Вопросы</span>'}</div><div class="meeting-body${chat ? " has-chat" : ""}"><div class="meeting-scene"><img class="meeting-audience" src="/audience-meeting-v1.png" alt="Слушатели в переговорной"><div class="self-view" hidden><video id="camera-preview" autoplay muted playsinline aria-label="Твоё видео" hidden></video><span class="self-name">Ты</span></div></div>${chat ? questionChat(p, segment, job) : ""}</div><div class="meeting-toolbar"><div class="meeting-devices">${devicesAvailable ? `<button class="device-control" type="button" data-action="toggle-mic" aria-pressed="false" title="Включить микрофон" ${!segment || job ? "disabled" : ""}>${deviceIcon("mic")}<span>Микрофон</span></button><button class="device-control" type="button" data-action="toggle-camera" aria-pressed="false" title="Включить камеру">${deviceIcon("camera")}<span>Камера</span></button>` : ""}</div><div class="meeting-controls" id="record-controls">${canRecord ? button(segment.kind === "answer" ? "Начать ответ" : "Начать выступление", "start-record", "primary", "disabled") : ""}</div><p class="meeting-status" id="record-status" role="status">${pendingSpeech ? (state.uploading ? "Сохраняем выступление…" : "Запись ещё не сохранена") : canRecord ? "Включи микрофон, чтобы начать" : "Выступление сохранено"}</p><div id="record-error" role="alert"></div><p id="camera-status" role="status"></p></div>`;
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
  if (p.report) return reportPage(p);
  if (guest && p.blob) return guestResult();
  const active = p.active_job || p.latest_job;
  if (active && ["pending", "running"].includes(active.status))
    return processingPage(p, active);
  const segment = nextSegment(p);
  const needQuestions =
    p.config.questions &&
    p.segments?.some((s) => s.kind === "speech") &&
    !p.questions?.length;
  if (segment || needQuestions) return meetingPage(p, guest);
  frame(
    `${practiceProgress(p, "report")}<section class="empty"><h1>Записи сохранены</h1><p>Всё готово для разбора выступления.</p>${active?.status === "failed" ? errorBox(active.error?.message || "Не удалось подготовить разбор. Попробуй ещё раз.") : ""}${button("Получить разбор", "report", "primary", state.providerReady ? "" : "disabled")}${!state.providerReady ? '<p class="caption">Сервис нейросети ещё не настроен. Записи сохранены в истории.</p>' : ""}</section>`,
  );
}
const stageLabels = {
  pending: "Ожидаем свободное место",
  transcribing: "Расшифровываем запись",
  transcription: "Расшифровываем запись",
  questions: "Готовим вопросы",
  analyzing: "Разбираем выступление",
  analysis: "Разбираем выступление",
  report: "Составляем разбор",
  running: "Обрабатываем запись",
};
function jobStage(stage) {
  return stage?.startsWith("transcription_")
    ? "Расшифровываем запись"
    : stageLabels[stage] || "Обрабатываем запись";
}
function processingPage(p, job) {
  if (job.kind === "questions") {
    meetingPage(p, false, job);
    pollJob(p.id, job.id);
    return;
  }
  frame(
    `${practiceProgress(p, job.kind)}<div class="processing"><span class="spinner" aria-hidden="true"></span><p class="eyebrow">Записи сохранены</p><h1>${job.kind === "questions" ? "Готовим вопросы по твоей речи" : "Собираем разбор выступления"}</h1><p id="job-status" role="status">${jobStage(job.stage)}</p><p class="caption">Можно оставить эту страницу или вернуться позже через историю. Обработка продолжится на сервере.</p><a href="#/history" class="button secondary">Открыть историю</a><div id="poll-error" role="alert"></div></div>`,
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
      if (status) status.textContent = jobStage(job.stage);
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
        "Этот браузер не поддерживает запись. Открой сайт в актуальном Chrome, Safari или Firefox.",
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
          onStatus: (result) => {
            if (!state.recording || state.liveCapture !== capture) return;
            const status = document.querySelector("#record-status");
            if (!status) return;
            const enabled = stream
              .getAudioTracks()
              .some((track) => track.enabled);
            status.textContent = !enabled
              ? "Микрофон выключен"
              : result.status === "unavailable"
                ? "Идёт запись. Распознаем речь после завершения"
                : result.recognized_words > 0
                  ? `Идёт запись. Распознано слов: ${result.recognized_words}`
                  : "Идёт запись. Распознаём речь фрагментами";
          },
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
  if (start) start.disabled = !live;
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
}
function updateCameraUI() {
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
      throw new Error("Камера недоступна в этом браузере.");
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
function closeMedia({ keepCamera = false, keepLive = false } = {}) {
  if (!keepCamera) closeCamera();
  clearInterval(state.timer);
  cancelAnimationFrame(state.raf);
  if (keepLive) return;
  state.liveCapture?.cancel();
  state.liveCapture = null;
  state.stream?.getTracks().forEach((t) => t.stop());
  state.stream = null;
  if (state.audioContext) {
    void state.audioContext.close().catch(() => {});
    state.audioContext = null;
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
  const p = state.practice,
    segment = nextSegment(p),
    duration = recordingLimit(p, segment);
  const withVideo = !!cameraLive();
  const types = withVideo
    ? ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"]
    : ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"];
  const type = types.find((t) => MediaRecorder.isTypeSupported(t));
  if (duration < 2) {
    closeMedia();
    document.querySelector("#record-error").innerHTML =
      errorBox(
        "Лимит аудио для этой тренировки исчерпан. Можно получить разбор сохранённых записей.",
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
              "Браузер не разрешил сохранить черновик. Не закрывай вкладку до сохранения записи.",
            );
        });
      }
    };
    recorder.onerror = () => {
      state.recordingError =
        "Запись прервалась из-за ошибки микрофона. Прослушай сохранённый фрагмент перед продолжением.";
    };
    recorder.onstop = async () => {
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
        interrupted: false,
        autoSave: segment.kind === "speech",
      };
      state.pendingPersisted = false;
      const capture = state.liveCapture;
      state.liveCapture = null;
      if (capture && segment.kind === "speech") {
        state.pending.liveCompletion = capture.finish().finally(() => {
          if (state.audioContext === capture.context)
            closeMedia({ keepCamera: p.config.questions });
        });
      } else capture?.cancel();
      closeMedia({
        keepCamera: segment.kind === "speech" && p.config.questions,
        keepLive: !!state.pending.liveCompletion,
      });
      await persistPending();
      if (segment.kind === "speech") void saveRecording();
      else showPending();
    };
    recorder.start(1000);
    state.recording = true;
    state.recordingWithVideo = withVideo;
    updateCameraUI();
    state.started = Date.now();
    document.querySelector("#record-status").textContent = "Идёт запись";
    if (segment.kind === "speech") {
      const live = state.liveCapture?.start();
      if (!live && state.user && state.providerReady)
        document.querySelector("#record-status").textContent =
          "Идёт запись. Распознаем речь после завершения";
    }
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
function saveLabel(p, pending) {
  if (pending.kind === "speech") return "Повторить сохранение";
  if (p.id === "guest") return "Перейти к разбору";
  if (pending.kind === "answer" && pending.index < p.questions.length)
    return "Сохранить и перейти к следующему вопросу";
  return "Сохранить и получить разбор";
}
async function continueAfterSave(p) {
  if (!state.user && p.id !== "guest") {
    rememberReturn(p.id);
    go("/login");
    return;
  }
  const version = state.routeVersion;
  practicePage(p);
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
      `<section class="narrow record-review"><h1>Тренировка больше недоступна</h1><p>Локальная запись сохранилась в браузере. Скачай её перед удалением черновика.</p>${playback(pending.url, pending.blob.type.startsWith("video/"))}<a class="button secondary" href="${escape(pending.url)}" download="моя-запись">Скачать черновик</a>${button("Удалить локальный черновик", "delete-local-draft", "text")}<a href="#/app">К тренировкам</a></section>`,
    );
    return;
  }
  if (pending.conflict) {
    frame(
      `<section class="narrow record-review"><h1>На этом этапе уже есть сохранённая запись</h1><p>Локальный черновик отличается от записи на сервере. Его можно прослушать и скачать перед продолжением.</p>${playback(pending.url, pending.blob.type.startsWith("video/"))}<a class="button secondary" href="${escape(pending.url)}" download="моя-запись">Скачать черновик</a>${button("Продолжить с записью на сервере", "use-server-recording")}</section>`,
    );
    return;
  }
  if (pending.kind === "speech") {
    meetingPage(state.practice, state.practice.id === "guest");
    if (state.recordingError)
      document.querySelector("#record-error").innerHTML = errorBox(
        state.recordingError,
      );
    return;
  }
  frame(
    `<section class="record-review narrow"><p class="eyebrow">${pending.kind === "answer" ? `Ответ на вопрос ${pending.index}` : "Тренировка"}</p><h1>${pending.interrupted ? "Запись прервалась" : pending.kind === "answer" ? "Ответ записан" : "Выступление записано"}</h1>${pending.interrupted ? "<p>Восстановили сохранённый фрагмент. Прослушай его перед продолжением.</p>" : ""}<div id="record-preview">${playback(pending.url, pending.blob.type.startsWith("video/"))}</div><div id="record-controls" class="actions">${!state.user && pending.ownerId ? button("Войти и продолжить", "reauth") : `${button(saveLabel(state.practice, pending), "save-record")}${button("Перезаписать", "discard-record", "secondary")}`}</div><p class="caption" id="record-status" role="status">${pendingPersistenceText()}</p><a class="quiet-link" href="${escape(pending.url)}" download="моя-запись">Скачать копию записи</a><div id="record-error" role="alert">${state.recordingError ? errorBox(state.recordingError) : ""}</div></section>`,
  );
}
function discardPending() {
  if (state.pending) URL.revokeObjectURL(state.pending.url);
  state.pending = null;
  state.pendingPersisted = false;
}
function pendingPersistenceText() {
  return state.pendingPersisted
    ? "Запись сохранена в этом браузере на сутки. Можно вернуться и продолжить тренировку."
    : "Запись остаётся в этой вкладке. Не закрывай её до сохранения на сервере.";
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
  if (needsPersist) await persistPending(pending);
  if (pending.kind === "speech") meetingPage(p, p.id === "guest");
  else
    document.querySelector("#record-controls").innerHTML =
      '<span class="caption" role="status">Сохраняем запись… Не закрывай страницу.</span>';
  try {
    if (p.id === "guest") {
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
    await clearAcceptedDraft(pending);
    discardPending();
    closeMedia({ keepCamera: pending.kind === "speech" && p.config.questions });
    state.uploading = false;
    await continueAfterSave(p);
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
          await continueAfterSave(saved);
          return;
        }
      } catch {}
    }
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
  if (path === "/landing") return landing();
  if (path === "/example") return go("/landing");
  if (path === "/privacy") return go("/landing");
  if (["/register", "/login", "/reset"].includes(path)) {
    if (state.user && path !== "/reset") {
      if (state.guest?.blob) return guestResult();
      go("/app");
      return;
    }
    authScreen(path.slice(1));
    return;
  }
  if (path === "/guest") return go(state.user ? "/app" : "/register");
  if (!state.user) {
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
        `<h1>Нет связи с сервером</h1>${errorBox("Авторизация и сохранение недоступны. Повтори подключение, чтобы войти в аккаунт.")} ${button("Повторить подключение", "reconnect", "secondary")}`,
      );
      return;
    }
    go("/login");
    return;
  }
  if (path === "/app") return setup();
  if (path === "/history") return history();
  const match = path.match(/^\/practice\/([^/]+)$/);
  if (match) {
    frame('<div class="loading" role="status">Загружаем тренировку…</div>');
    try {
      const p = await api.practice(decodeURIComponent(match[1]));
      if (version !== state.routeVersion) return;
      state.practice = p;
      await restorePending(p);
      if (version !== state.routeVersion || !state.user) return;
      forgetReturn();
      practicePage(p);
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
      state.providerReady = data.provider_ready ?? state.providerReady;
      state.inviteRequired = data.registration_requires_invite ?? state.inviteRequired;
      state.online = true;
      frame(`<div class="loading" role="status">${mode === "register" ? "Аккаунт создан. Открываем тренировку…" : "Вход выполнен. Открываем тренировку…"}</div>`);
      await resumeAfterLogin();
    } else if (form.id === "setup-form") {
      const config = {
        scenario: body.scenario,
        topic: body.topic.trim(),
        duration: Number(body.duration),
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
          state.uploading
        ) {
          notify("Сначала сохрани или отмени текущую запись.");
          return;
        }
        await api.logout();
        discardPending();
        state.user = null;
        state.practice = null;
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
      case "open-answer":
        state.activeAnswer = `${state.practice.id}:${nextSegment(state.practice).index}`;
        meetingPage(state.practice);
        if (window.matchMedia("(max-width: 680px)").matches)
          queueMicrotask(() =>
            document
              .querySelector(".chat-message.is-current")
              ?.scrollIntoView({ block: "center", behavior: "instant" }),
          );
        break;
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
        startRecording();
        break;
      case "stop-record":
        stopRecording();
        break;
      case "save-record":
        await saveRecording();
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
            "Удалить локальный черновик и продолжить с записью на сервере?",
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
            "Удалить локальный черновик? Сначала скачай запись, если она нужна.",
          )
        )
          return;
        await clearRecordingDraft(state.pending);
        await clearDraft(state.pending.clientKey);
        discardPending();
        go("/app");
        break;
      case "questions":
      case "report": {
        target.disabled = true;
        const p = state.practice;
        const version = state.routeVersion;
        try {
          const job = await api.startJob(p.id, name);
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
      case "repeat": {
        const selected = Number(
          document.querySelector('input[name="repeat-focus"]:checked')?.value ||
            0,
        );
        const recommendation = repeatChoices(state.practice.report)[selected];
        if (!state.user.onboarding_completed) {
          const data = await api.completeOnboarding();
          state.user = data.user;
        }
        const p = await api.createPractice({
          ...state.practice.config,
          criteria: recommendation?.text || state.practice.config.criteria,
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
    state.providerReady = me.provider_ready;
    state.inviteRequired = me.registration_requires_invite;
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
    (state.guest?.blob && !state.guestPersisted)
  ) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("session-expired", sessionExpired);
installTypography([app, document.querySelector("#toast")]);
void initialize();
