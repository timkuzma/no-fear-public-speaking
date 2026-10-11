import { api, demoResult } from "./api.js";
const app = document.querySelector("#app");
const state = {
  user: null,
  providerReady: false,
  inviteRequired: false,
  online: true,
  practice: null,
  guest: null,
  recorder: null,
  stream: null,
  audioContext: null,
  recording: false,
  pending: null,
  recordingError: "",
  timer: null,
  raf: null,
  poll: null,
  routeVersion: 0,
  uploading: false,
};
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
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
  return `<a class="button ${cls}" href="#${state.user ? "/app" : "/register"}">${text}<span aria-hidden="true">↗</span></a>`;
}
function header() {
  return `<header class="header"><a class="brand" href="#/landing"><span class="brand-symbol" aria-hidden="true">с.</span><span>сцена<br>без страха</span></a><nav aria-label="Основная навигация">${state.user ? `<a href="#/app">Тренировка</a><a href="#/history">История</a>${button("Выйти", "logout", "text")}` : `<a href="#/example">Пример разбора</a><a href="#/login">Войти</a>`}</nav></header>`;
}
function frame(content, kind = "workspace") {
  app.innerHTML = `${header()}<main id="main" class="${kind}" tabindex="-1">${content}</main><footer><span>Сцена без страха</span><a href="#/privacy">Записи и данные</a><span>Пилотная версия</span></footer>`;
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
    `<section class="hero"><div class="hero-copy"><p class="eyebrow">Твоя репетиция перед важным днём</p><h1>Сначала здесь.<br><span>Потом перед</span><br>аудиторией.</h1><p class="hero-description">Отрепетируй выступление, ответь на вопросы и получи разбор: что уже получается и что попробовать в следующей попытке.</p><div class="actions">${startLink()}<a class="quiet-link" href="#/example">Посмотреть разбор <span aria-hidden="true">→</span></a></div>${!state.user ? '<p class="caption">Для сохранения тренировок сначала создай аккаунт.</p>' : ""}</div><div class="hero-visual"><img src="/audience-hall.jpg" width="1200" height="800" alt="Зрительный зал: место твоего будущего выступления" fetchpriority="high"><div class="visual-caption"><span class="dot"></span>Здесь можно попробовать ещё раз</div><div class="floating-note"><span class="eyebrow">Следующая попытка</span><strong>Одна мысль.<br>Один убедительный пример.</strong><span>Тренируй конкретный навык</span></div></div><div class="hero-index" aria-hidden="true">01 / ПРАКТИКА</div></section><section class="method"><div><p class="eyebrow">Как проходит тренировка</p><h2>Поговори.<br>Прочитай разбор.<br>Попробуй снова.</h2></div><ol class="step-list"><li><span>01</span><div><h3>Выбери задачу</h3><p>Выступление, защита проекта или свободная речь. Для знакомства начни с одной минуты.</p></div></li><li><span>02</span><div><h3>Запиши выступление</h3><p>Говори в своём темпе. При желании ответь на три вопроса по содержанию речи.</p></div></li><li><span>03</span><div><h3>Возьми одну рекомендацию</h3><p>Разбор опирается на расшифровку. Найди фрагмент, который хочешь улучшить, и запиши новую попытку.</p></div></li></ol></section><section class="landing-example"><div><p class="eyebrow">Что ты получишь</p><h2>Понятно, какой<br>фрагмент доработать.</h2><p>Наблюдение, цитата из речи и действие для следующей попытки.</p><a class="quiet-link" href="#/example">Открыть пример целиком →</a></div><article class="report-preview"><span class="tag">Демонстрационный пример</span><p class="eyebrow">Что попробовать</p><h3>Покажи, как это работает</h3><blockquote>«Так подготовка станет удобнее»</blockquote><p>После главной мысли приведи один случай: что делает пользователь и какой результат получает.</p></article></section><section class="faq-section"><h2>Перед началом</h2><details><summary>Что именно анализирует нейросеть?</summary><p>Содержание расшифровки: главную мысль, аргументы, структуру и ответы на вопросы. Разбор может ошибаться. Он не оценивает личность, эмоции или жесты.</p></details><details><summary>Можно попробовать без аккаунта?</summary><p>Да. В гостевом режиме можно записать и прослушать речь прямо в браузере. Запись не отправляется на сервер и исчезнет после закрытия страницы. Разбор нейросети и история доступны после входа.</p><a href="#/guest">Попробовать запись без аккаунта →</a></details><details><summary>Что происходит с моей записью?</summary><p>В аккаунте запись хранится на сервере. Для разбора аудио передаётся сервису расшифровки, а текст — нейросети. Можно удалить тренировку вместе с записью.</p><a href="#/privacy">Подробнее о данных →</a></details></section><section class="closing"><p class="eyebrow">До выступления есть время попробовать</p><h2>Начни с минуты<br>о своей идее.</h2>${startLink()}</section>`,
    "landing",
  );
}
function authScreen(mode) {
  const register = mode === "register",
    reset = mode === "reset";
  frame(
    `<div class="auth-layout"><div class="auth-intro"><p class="eyebrow">${reset ? "Восстановление доступа" : "Репетиция начинается здесь"}</p><h1>${reset ? "Вернись к своим тренировкам." : register ? "Место для<br>первой попытки." : "Продолжим<br>тренировку."}</h1><p>${reset ? "Для пилота организатор выдаёт одноразовый код после проверки владельца аккаунта." : register ? "Сохрани выступление и возвращайся к разбору после каждой попытки." : "Твои записи и разборы останутся в истории."}</p></div><section class="auth-panel"><h2>${reset ? "Новый пароль" : register ? "Создай аккаунт" : "Войди в аккаунт"}</h2><form id="auth-form" data-mode="${mode}">${register ? '<label>Имя<input name="name" autocomplete="given-name" maxlength="80" required></label>' : ""}${reset ? '<label>Одноразовый код<input name="token" autocomplete="off" required></label>' : '<label>Электронная почта<input type="email" name="email" autocomplete="email" maxlength="254" required></label>'}<label>${reset ? "Новый пароль" : "Пароль"}<input type="password" name="password" autocomplete="${register || reset ? "new-password" : "current-password"}" ${register || reset ? 'minlength="10"' : ""} maxlength="128" required></label>${register || reset ? '<p class="field-hint">Не менее 10 символов.</p>' : ""}${register ? `<label>Для чего тренируешься?<select name="role"><option value="student">Учёба и защита проекта</option><option value="professional">Работа и выступления</option><option value="other">Другое</option></select></label>${state.inviteRequired ? '<label>Код приглашения<input name="invite_code" autocomplete="off" required></label>' : ""}<label class="check"><input type="checkbox" name="consent" required><span>Соглашаюсь на хранение записи и передачу аудио и текста сервисам нейросети для разбора. <a href="#/privacy">Условия обработки данных</a></span></label>` : ""}<div class="form-error" role="alert"></div><button class="button primary" type="submit">${reset ? "Сохранить пароль" : register ? "Создать аккаунт" : "Войти"} <span aria-hidden="true">→</span></button></form><p class="auth-links">${reset ? '<a href="#/login">Вернуться ко входу</a>' : register ? 'Уже есть аккаунт? <a href="#/login">Войти</a>' : '<a href="#/register">Создать аккаунт</a> · <a href="#/reset">Восстановить доступ</a>'}</p>${register ? '<a class="quiet-link" href="#/guest">Попробовать запись без аккаунта →</a>' : ""}</section></div>`,
  );
}
function privacy() {
  frame(
    `<section class="narrow prose"><p class="eyebrow">Пилотная версия</p><h1>Записи и данные</h1><h2>Что сохраняется</h2><p>Имя, электронная почта, настройки тренировок, записи, расшифровки и разборы. Для входа сервер хранит хеш пароля. Другие пользователи не получают доступ к твоим тренировкам.</p><h2>Как появляется разбор</h2><p>Аудио передаётся внешнему сервису расшифровки. Текст речи и выбранные критерии передаются нейросети. Разбор основан на содержании текста и может содержать ошибки.</p><h2>Как удалить запись</h2><p>Открой историю и удали тренировку. Вместе с ней сервер удалит запись, расшифровку и разбор. Удаление не отменяет обработку, уже выполненную внешним сервисом, и не удаляет данные из ранее созданных резервных копий.</p><h2>Гостевой режим</h2><p>Гостевая запись остаётся в памяти этой страницы. Она не отправляется на сервер и не сохраняется после закрытия или обновления страницы.</p><h2>Обратная связь</h2><p>Оценку разбора и комментарий можно отправить с его страницы. Не добавляй в комментарий пароли или данные других людей.</p><a class="button secondary" href="#/landing">На главную</a></section>`,
  );
}
function savedTopic() {
  try {
    return sessionStorage.getItem("practice-topic") || "";
  } catch {
    return "";
  }
}
function setup(guest = false) {
  frame(
    `<div class="page-heading"><p class="eyebrow">${guest ? "Попробовать без аккаунта" : "Рабочее пространство"}</p><h1>${guest ? "Послушай свою речь." : `Привет${state.user?.name ? ", " + escape(state.user.name) : ""}.<br>Что будем репетировать?`}</h1></div>${guest ? '<div class="notice">Гостевая запись остаётся только на этой странице. Для разбора нейросети и истории <a href="#/register">создай аккаунт</a>.</div>' : !state.providerReady ? '<div class="notice">Сервис нейросети ещё не настроен. Можно сохранить запись; разбор станет доступен после подключения сервиса.</div>' : ""}<div class="setup-layout">${!guest && !state.user.onboarding_completed ? `<aside class="starter"><span class="tag">Первая тренировка · 60 секунд</span><h2>Объясни идею<br>своего проекта.</h2><p>Какую проблему он решает? Кому поможет? Назови один пример применения.</p>${button("Начать с этого упражнения", "starter")}<p class="caption">После разбора выбери одну рекомендацию и повтори попытку.</p>${button("Выбрать свою задачу", "skip-onboarding", "text")}</aside>` : `<aside class="starter"><p class="eyebrow">Один фокус на попытку</p><h2>Главная мысль.<br>Пример.<br>Вывод.</h2><p>${guest ? "Выбери тему, запиши выступление и прослушай его. Попробуй объяснить одну мысль конкретным примером." : "Выбери тему, которую предстоит объяснить аудитории. После разбора повтори выступление с одной рекомендацией."}</p></aside>`}<form id="setup-form" data-guest="${guest}" class="setup-form"><h2>${guest ? "Твоя пробная запись" : "Настроить тренировку"}</h2><fieldset><legend>Сценарий</legend><div class="scenario-options"><label><input type="radio" name="scenario" value="speech" checked><span><strong>Выступление</strong><small>Речь для аудитории</small></span></label><label><input type="radio" name="scenario" value="defense"><span><strong>Защита проекта</strong><small>Идея и аргументы</small></span></label><label><input type="radio" name="scenario" value="free"><span><strong>Свободная речь</strong><small>Тема на твой выбор</small></span></label></div></fieldset><label>Тема выступления<input name="topic" maxlength="300" placeholder="Например, идея моего проекта" required value="${escape(savedTopic())}"></label><label>Продолжительность<select name="duration"><option value="1">1 минута</option><option value="3">3 минуты</option><option value="5" selected>5 минут</option><option value="10">10 минут</option></select></label>${guest ? "" : '<label class="check"><input type="checkbox" name="questions" checked><span>После выступления ответить на три вопроса аудитории</span></label><p class="field-hint">До 10 минут аудио на тренировку. С вопросами: выступление до 7 минут и три ответа до минуты каждый.</p><label>На что обратить внимание <span class="optional">необязательно</span><textarea name="criteria" maxlength="2000" rows="3" placeholder="Например, понятны ли аргументы и вывод"></textarea></label>'}<div class="form-error" role="alert"></div><button type="submit" class="button primary">Перейти к записи <span aria-hidden="true">→</span></button></form></div>`,
  );
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
      `<div class="page-heading row"><div><p class="eyebrow">Твои тренировки</p><h1>История</h1></div><a class="button primary" href="#/app">Новая тренировка ↗</a></div>${data.items.length ? `<div class="history-list">${data.items.map((p) => `<article class="history-item"><div><p class="caption">${escape(date(p.created_at))}</p><h2><a href="#/practice/${encodeURIComponent(p.id)}">${escape(p.config?.topic || "Тренировка")}</a></h2><span class="tag ${p.status === "ready" ? "green" : ""}">${{ draft: "Запись и подготовка", processing: "Обрабатывается", ready: "Разбор готов", failed: "Нужна повторная обработка" }[p.status] || escape(p.status)}</span></div><div class="actions"><a class="button secondary" href="#/practice/${encodeURIComponent(p.id)}">${p.status === "ready" ? "Посмотреть разбор" : "Продолжить"}</a>${button("Удалить", "delete", "text", `data-id="${escape(p.id)}"`)}</div></article>`).join("")}</div>${`<div class="actions">${offset > 0 ? button("← Предыдущие", "history-page", "secondary", `data-offset="${Math.max(0, offset - 30)}"`) : ""}${offset + data.items.length < data.total ? button("Следующие →", "history-page", "secondary", `data-offset="${offset + 30}"`) : ""}</div>`}` : `<div class="empty"><h2>Здесь появится твоя первая попытка.</h2><p>Запиши выступление. Сохранённая запись и разбор останутся в истории.</p><a class="button primary" href="#/app">Начать тренировку</a></div>`}`,
    );
  } catch (error) {
    if (version === state.routeVersion)
      frame(
        `<h1>История</h1>${errorBox(errorText(error))}${button("Попробовать ещё раз", "refresh", "secondary")}`,
      );
  }
}
function reportMarkup(report, preview = false) {
  return `${report.demo ? '<div class="notice">Демонстрационный пример. Этот разбор не связан с твоей записью.</div>' : ""}<section class="report-insight"><p class="eyebrow">Главное в этой попытке</p><h2>${escape(report.insight)}</h2></section><div class="report-columns"><section><p class="eyebrow">Уже получается</p>${(report.strengths || []).map((item) => reportItem(item, "strength")).join("") || "<p>Для вывода не хватило данных.</p>"}</section><section><p class="eyebrow">Что попробовать в следующей попытке</p>${(report.recommendations || []).map((item) => reportItem(item, "recommendation")).join("") || "<p>Конкретных рекомендаций пока нет.</p>"}</section></div>${report.metrics?.length ? `<section class="report-metrics"><h2>Наблюдения</h2>${report.metrics.map((m) => `<article><span class="eyebrow">${escape(m.label)}</span><h3>${escape(m.title)}</h3><p>${escape(m.text)}</p></article>`).join("")}</section>` : ""}${report.criteria?.length ? `<section class="report-section"><h2>Выбранные критерии</h2>${report.criteria.map((c) => `<article class="criterion"><strong>${escape(c.criterion)}</strong><span class="tag">${{ met: "Есть в речи", partial: "Частично", not_met: "Не найдено", unknown: "Недостаточно данных" }[c.status] || "Недостаточно данных"}</span><p>${escape(c.evidence)}</p></article>`).join("")}</section>` : ""}${report.limitations?.length ? `<div class="notice"><strong>Границы разбора</strong><ul>${report.limitations.map((l) => `<li>${escape(l)}</li>`).join("")}</ul></div>` : ""}<details class="transcript"><summary>Расшифровка речи</summary><p>${escape(report.transcript)}</p></details>${preview ? `<div class="actions">${startLink("Попробовать свою речь")}<a class="button secondary" href="#/guest">Записать без аккаунта</a></div>` : ""}`;
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
  return `<article class="report-item ${cls}"><h3>${escape(item.title)}</h3>${item.evidence ? `<blockquote>${escape(item.evidence)}</blockquote>` : ""}<p>${escape(item.text)}</p></article>`;
}
function reportPage(p) {
  if (!state.user) {
    go("/login");
    return;
  }
  frame(
    `<div class="page-heading"><p class="eyebrow">Разбор · ${escape(date(p.created_at))}</p><h1>${escape(p.config.topic || "Твоя тренировка")}</h1></div>${button("Скачать разбор", "download-report", "secondary")}${reportMarkup(p.report)}<section class="report-section"><h2>Твои записи</h2>${mediaMarkup(p)}</section><section class="next-attempt"><div><p class="eyebrow">Примени рекомендацию</p><h2>Ещё одна попытка.<br>Один выбранный фокус.</h2><p>${escape(p.report.recommendations?.[0]?.text || "Повтори выступление и сравни свою речь с прошлой попыткой.")}</p></div>${button("Повторить тренировку", "repeat")}</section>${!state.user.onboarding_completed ? `<div class="notice"><p>Ты прошёл полный цикл. Теперь выбери одну рекомендацию выше и попробуй применить её в следующей записи.</p>${button("Завершить знакомство", "finish-onboarding", "secondary")}</div>` : ""}<form id="feedback-form" class="feedback-form"><h2>Был ли разбор полезен?</h2><fieldset><legend>Оценка от 1 до 5</legend><div class="ratings">${[1, 2, 3, 4, 5].map((n) => `<label><input type="radio" name="rating" value="${n}" required><span>${n}</span></label>`).join("")}</div></fieldset><label>Что стоит улучшить? <span class="optional">необязательно</span><textarea name="text" rows="3" maxlength="2000"></textarea></label><div class="form-error" role="alert"></div><button type="submit" class="button secondary">Отправить отзыв</button></form>`,
  );
}
function mediaMarkup(p) {
  return `<div class="media-list">${(p.segments || [])
    .map((segment) => {
      const url =
        segment.media_url ||
        `/api/practices/${encodeURIComponent(p.id)}/segments/${encodeURIComponent(segment.id)}/media`;
      return `<article><strong>${segment.kind === "speech" ? "Выступление" : `Ответ ${escape(segment.index)}`}</strong><audio controls preload="metadata" src="${escape(url)}"></audio><a href="${escape(url)}?download=true" download>Скачать запись</a></article>`;
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
function practicePage(p, guest = false) {
  state.practice = p;
  if (p.report) {
    reportPage(p);
    return;
  }
  const active = p.active_job || p.latest_job;
  if (active && ["pending", "running"].includes(active.status)) {
    processingPage(p, active);
    return;
  }
  const segment = nextSegment(p);
  const needQuestions =
    p.config.questions &&
    p.segments?.some((s) => s.kind === "speech") &&
    !p.questions?.length;
  frame(
    `<div class="page-heading row"><div><p class="eyebrow">${guest ? "Гостевая запись" : segment?.kind === "answer" ? `Вопрос ${segment.index} из ${p.questions.length}` : "Тренировка"} · ${escape(p.config.topic)}</p><h1>${needQuestions ? "Выступление сохранено." : segment?.kind === "answer" ? "Ответь аудитории." : segment ? "Время попробовать." : "Записи сохранены."}</h1></div>${!guest ? '<a class="quiet-link" href="#/history">К истории →</a>' : ""}</div>${guest ? '<div class="notice">Запись хранится только в этой вкладке. Нейросеть её не анализирует.</div>' : ""}${active?.status === "failed" || p.status === "failed" ? errorBox(active?.error?.message || "Обработка не завершилась. Записи сохранены. Можно попробовать ещё раз.") : ""}${segment ? `<section class="record-stage"><div class="record-prompt"><p class="eyebrow">${segment.kind === "answer" ? "Вопрос по твоему выступлению" : "Тема выступления"}</p><h2>${escape(segment.kind === "answer" ? p.questions[segment.index - 1] : p.config.topic)}</h2><p>${segment.kind === "answer" ? "Сначала дай прямой ответ, затем поясни его одним примером. На ответ — до 1 минуты." : "Обозначь главную мысль, подкрепи её примером и заверши выводом. Можно остановиться раньше таймера."}</p><span class="tag">${`До ${time(recordingLimit(p, segment))}`}</span>${segment.kind === "speech" && p.config.criteria ? `<div class="practice-focus"><p class="eyebrow">Фокус этой попытки</p><p>${escape(p.config.criteria)}</p></div>` : ""}</div><div class="recorder-panel"><div class="timer" id="record-timer">${time(recordingLimit(p, segment))}</div><div class="sound-meter" aria-label="Уровень звука"><span id="sound-level"></span></div><p id="record-status" role="status">Нажми «Проверить микрофон», затем начни запись.</p><div id="record-controls" class="actions">${button("Проверить микрофон", "check-mic", "secondary")}</div><div id="record-error" role="alert"></div><div id="record-preview"></div></div></section>` : `<section class="empty"><h2>${needQuestions ? "Теперь подготовим вопросы по твоей речи." : guest ? "Прослушай свою попытку." : "Можно переходить к разбору."}</h2><p>${needQuestions ? "Запись сохранена. Подготовка вопросов может занять несколько минут." : guest ? "Для сохранения истории и разбора своей речи создай аккаунт." : p.segments?.some((s) => s.kind === "answer") ? "Нейросеть разберёт содержание выступления и сохранённые ответы на вопросы." : "Нейросеть разберёт содержание выступления."}</p>${guest ? `${startLink("Создать аккаунт")}${button("Записать снова", "guest-again", "secondary")}` : button(needQuestions ? "Подготовить вопросы" : "Получить разбор", needQuestions ? "questions" : "report", "primary", state.providerReady ? "" : "disabled")}${!guest && !state.providerReady ? '<p class="caption">Сервис нейросети ещё не настроен. Записи уже сохранены в истории.</p>' : ""}</section>`}${p.segments?.length ? `<section class="report-section"><h2>Сохранённые записи</h2>${mediaMarkup(p)}</section>` : ""}`,
  );
  if (state.pending) showPending();
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
  frame(
    `<div class="processing"><span class="spinner" aria-hidden="true"></span><p class="eyebrow">Записи сохранены</p><h1>${job.kind === "questions" ? "Готовим вопросы<br>по твоей речи." : "Собираем разбор<br>выступления."}</h1><p id="job-status" role="status">${jobStage(job.stage)}</p><p class="caption">Можно оставить эту страницу или вернуться позже через историю. Обработка продолжится на сервере.</p><a href="#/history" class="button secondary">Открыть историю</a><div id="poll-error" role="alert"></div></div>`,
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
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw new Error(
        "Этот браузер не поддерживает запись. Открой сайт в актуальном Chrome, Safari или Firefox.",
      );
    closeMedia();
    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });
    if (version !== state.routeVersion) {
      closeMedia();
      return;
    }
    const Context = window.AudioContext || window.webkitAudioContext;
    if (Context) {
      state.audioContext = new Context();
      await state.audioContext.resume();
      const source = state.audioContext.createMediaStreamSource(state.stream),
        analyser = state.audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const draw = () => {
        analyser.getByteTimeDomainData(samples);
        let power = 0;
        for (const x of samples) power += (x - 128) ** 2;
        const level = Math.min(1, Math.sqrt(power / samples.length) / 30);
        const meter = document.querySelector("#sound-level");
        if (meter) meter.style.transform = `scaleX(${level})`;
        state.raf = requestAnimationFrame(draw);
      };
      draw();
    }
    document.querySelector("#record-status").textContent =
      "Произнеси пару слов: полоска должна двигаться. Запись ещё не началась.";
    document.querySelector("#record-controls").innerHTML = button(
      "Начать запись",
      "start-record",
    );
    document.querySelector("#record-error").textContent = "";
  } catch (error) {
    closeMedia();
    if (version !== state.routeVersion) return;
    document.querySelector("#record-error").innerHTML = errorBox(
      error.name === "NotAllowedError"
        ? "Доступ к микрофону закрыт. Разреши его в настройках сайта и повтори проверку."
        : error.name === "NotFoundError"
          ? "Микрофон не найден. Подключи устройство и повтори проверку."
          : errorText(error),
    );
  }
}
function closeMedia() {
  clearInterval(state.timer);
  cancelAnimationFrame(state.raf);
  state.stream?.getTracks().forEach((t) => t.stop());
  state.stream = null;
  if (state.audioContext) {
    void state.audioContext.close().catch(() => {});
    state.audioContext = null;
  }
}
function startRecording() {
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
  const types = [
    "audio/webm;codecs=opus",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
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
  state.recordingError = "";
  try {
    const recorder = new MediaRecorder(
      state.stream,
      type ? { mimeType: type } : undefined,
    );
    state.recorder = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onerror = () => {
      state.recordingError =
        "Запись прервалась из-за ошибки микрофона. Прослушай сохранённый фрагмент перед продолжением.";
    };
    recorder.onstop = () => {
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
      };
      closeMedia();
      showPending();
    };
    recorder.start(1000);
    state.recording = true;
    state.started = Date.now();
    document.querySelector("#record-status").textContent =
      "Идёт запись. Можно закончить раньше.";
    document.querySelector("#record-controls").innerHTML = button(
      "Закончить запись",
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
function showPending() {
  const pending = state.pending;
  if (!pending) return;
  const controls = document.querySelector("#record-controls"),
    preview = document.querySelector("#record-preview");
  if (!controls || !preview) return;
  document.querySelector("#record-status").textContent =
    "Запись завершена. Прослушай её перед сохранением.";
  controls.innerHTML =
    button(
      state.practice.id === "guest" ? "Оставить запись" : "Сохранить запись",
      "save-record",
    ) + button("Перезаписать", "discard-record", "secondary");
  preview.innerHTML = `<audio controls src="${escape(pending.url)}"></audio><a class="quiet-link" href="${escape(pending.url)}" download="моя-запись">Скачать копию записи</a><p class="caption">${state.practice.id === "guest" ? "Запись останется только в этой вкладке." : "Пока запись находится только в этой вкладке. Нажми «Сохранить запись», чтобы отправить её на сервер."}</p>`;
  if (state.recordingError)
    document.querySelector("#record-error").innerHTML = errorBox(
      state.recordingError,
    );
}
function discardPending() {
  if (state.pending) URL.revokeObjectURL(state.pending.url);
  state.pending = null;
}
async function saveRecording() {
  if (!state.pending || state.uploading) return;
  const pending = state.pending,
    p = state.practice;
  state.uploading = true;
  document.querySelector("#record-controls").innerHTML =
    '<span class="caption" role="status">Сохраняем запись… Не закрывай страницу.</span>';
  try {
    if (p.id === "guest") {
      p.segments = [{ kind: "speech", index: 0, media_url: pending.url }];
      state.guest = p;
      state.pending = null;
      practicePage(p, true);
      return;
    }
    const saved = await api.upload(
      p.id,
      pending.blob,
      pending.kind,
      pending.index,
    );
    p.segments.push(saved);
    p.status = "draft";
    p.latest_job = null;
    discardPending();
    closeMedia();
    practicePage(p);
  } catch (error) {
    if (error.status === 409) {
      try {
        const saved = await api.practice(p.id);
        if (
          saved.segments.some(
            (s) => s.kind === pending.kind && Number(s.index) === pending.index,
          )
        ) {
          discardPending();
          practicePage(saved);
          return;
        }
      } catch {}
    }
    showPending();
    document.querySelector("#record-error").innerHTML = errorBox(
      `${errorText(error)} Запись остаётся в этой вкладке.`,
    );
  } finally {
    state.uploading = false;
  }
}
async function navigate() {
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
      !confirm(
        "Несохранённая запись останется только в этой вкладке. Перейти на другую страницу и потерять её?",
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
    discardPending();
  }
  closeMedia();
  clearTimeout(state.poll);
  window.scrollTo({ top: 0, behavior: "instant" });
  const version = ++state.routeVersion;
  const path = route();
  if (path === "/landing") return landing();
  if (path === "/example") {
    frame(
      `<p class="eyebrow">Знакомство с результатом</p><h1>Пример разбора</h1>${reportMarkup(demoResult(), true)}`,
    );
    return;
  }
  if (path === "/privacy") return privacy();
  if (["/register", "/login", "/reset"].includes(path)) {
    authScreen(path.slice(1));
    return;
  }
  if (path === "/guest") {
    if (state.guest) practicePage(state.guest, true);
    else setup(true);
    return;
  }
  if (!state.user) {
    if (!state.online) {
      frame(
        `<h1>Нет связи с сервером</h1>${errorBox("Авторизация и сохранение недоступны. Можно повторить подключение или попробовать гостевую запись.")} ${button("Повторить подключение", "reconnect", "secondary")}<a class="button secondary" href="#/guest">Гостевая запись</a>`,
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
      if (version === state.routeVersion) practicePage(p);
    } catch (error) {
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
              consent: body.consent === "on",
            })
          : await api.login({ ...body, email: body.email.trim() });
      state.user = data.user;
      const me = await api.me();
      state.user = me.user;
      state.providerReady = me.provider_ready;
      state.inviteRequired = me.registration_requires_invite;
      state.online = true;
      go("/app");
    } else if (form.id === "setup-form") {
      const config = {
        scenario: body.scenario,
        topic: body.topic.trim(),
        duration: Number(body.duration),
        questions: body.questions === "on",
        criteria: body.criteria?.trim() || "",
      };
      if (!config.topic) throw new Error("Напиши тему выступления.");
      try {
        sessionStorage.setItem("practice-topic", config.topic);
      } catch {}
      if (form.dataset.guest === "true") {
        state.guest = {
          id: "guest",
          config,
          segments: [],
          questions: [],
          report: null,
        };
        practicePage(state.guest, true);
      } else {
        const p = await api.createPractice(config);
        go(`/practice/${encodeURIComponent(p.id)}`);
      }
    } else if (form.id === "feedback-form") {
      await api.feedback(state.practice.id, {
        rating: Number(body.rating),
        text: body.text?.trim() || "",
      });
      form.innerHTML =
        "<h2>Спасибо за отзыв.</h2><p>Он поможет доработать следующие разборы.</p>";
    }
  } catch (e) {
    error.textContent = errorText(e);
  } finally {
    submit.disabled = false;
  }
}
async function action(event) {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  target.disabled = true;
  const name = target.dataset.action;
  try {
    switch (name) {
      case "history-page":
        await history(Number(target.dataset.offset));
        break;
      case "download-report":
        downloadReport(state.practice);
        break;
      case "refresh":
        await navigate();
        break;
      case "reconnect":
        await initialize();
        break;
      case "logout":
        if (state.recording || state.pending || state.uploading) {
          notify("Сначала сохрани или отмени текущую запись.");
          return;
        }
        await api.logout();
        state.user = null;
        state.practice = null;
        go("/landing");
        break;
      case "starter": {
        const p = await api.createPractice({
          scenario: "defense",
          topic: "Идея моего проекта: какую проблему он решает и кому поможет",
          duration: 1,
          questions: true,
          criteria: "Понятны ли проблема, решение и пример применения",
        });
        go(`/practice/${encodeURIComponent(p.id)}`);
        break;
      }
      case "skip-onboarding":
      case "finish-onboarding": {
        const data = await api.completeOnboarding();
        state.user = data.user;
        notify("Знакомство завершено.");
        await navigate();
        break;
      }
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
        discardPending();
        practicePage(state.practice, state.practice.id === "guest");
        break;
      case "questions":
      case "report": {
        target.disabled = true;
        const job = await api.startJob(state.practice.id, name);
        processingPage(state.practice, job);
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
        notify("Тренировка удалена.");
        await history();
        break;
      }
      case "repeat": {
        const p = await api.createPractice({
          ...state.practice.config,
          criteria:
            state.practice.report.recommendations?.[0]?.text ||
            state.practice.config.criteria,
        });
        go(`/practice/${encodeURIComponent(p.id)}`);
        break;
      }
      case "guest-again":
        state.guest?.segments.forEach((s) => URL.revokeObjectURL(s.media_url));
        state.guest = null;
        setup(true);
        break;
    }
  } catch (error) {
    notify(errorText(error));
    target.disabled = false;
  } finally {
    if (target.isConnected) target.disabled = false;
  }
}
async function initialize() {
  frame('<div class="loading" role="status">Открываем сцену…</div>');
  try {
    const me = await api.me();
    state.user = me.user;
    state.providerReady = me.provider_ready;
    state.inviteRequired = me.registration_requires_invite;
    state.online = true;
  } catch {
    state.online = false;
  }
  await navigate();
}
app.addEventListener("submit", submitForm);
app.addEventListener("click", action);
document.querySelector(".skip-link").addEventListener("click", (event) => {
  event.preventDefault();
  document.querySelector("#main")?.focus();
});
window.addEventListener("hashchange", () => void navigate());
window.addEventListener("beforeunload", (event) => {
  if (state.recording || state.pending || state.uploading) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("session-expired", () => {
  state.user = null;
  const currentHeader = document.querySelector(".header");
  if (currentHeader) currentHeader.outerHTML = header();
  if (state.pending || state.recording || state.uploading) {
    notify("Сессия завершилась. Скачай копию записи и войди снова.");
    const message = document.querySelector("#record-error");
    if (message)
      message.innerHTML =
        errorBox(
          "Сессия завершилась. Скачай копию записи перед повторным входом.",
        ) + '<a href="#/login">Войти снова</a>';
  } else go("/login");
});
void initialize();
