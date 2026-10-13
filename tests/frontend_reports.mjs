import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../public/app.js", import.meta.url), "utf8")
  .replace(/^import[\s\S]*?;\n/gm, "")
  .split('app.addEventListener("submit"')[0];
const created = [];
let checked = { value: "1" };
const context = vm.createContext({
  document: { querySelector: (selector) => selector === 'input[name="repeat-focus"]:checked' ? checked : {} },
  location: { hash: "#/app" }, window: { scrollTo() {} },
  sessionStorage: { setItem() {}, removeItem() {} }, clearTimeout, setTimeout,
  api: { createPractice: async (config) => { created.push(config); return { id: "next" }; } },
});
vm.runInContext(source + `
  frame = content => globalThis.markup = content;
  notify = message => globalThis.notification = message;
  pollJob = () => {};
  closeMedia = () => {};
  globalThis.ui = { state, reportMarkup, reportPage, reportText, repeatChoices, repeatPanel, action, processingPage };
`, context);
const report = {
  schema_version: 2, primary_recommendation_index: 1, insight: "Ignored independent insight",
  strengths: [{ title: "Связь", observation: "Начало связано с концом", text: "Начало связано с концом", evidence: "Сосед помог мне", segment_index: 0, origin: "speech" }],
  recommendations: [
    { title: "Речь", observation: "Предмет назван", text: "legacy fallback duplicate", action: "Повтори название", evidence: "Это кэш", segment_index: 0, origin: "speech" },
    { title: "Ответ", observation: "Цена пока неизвестна", text: "legacy fallback duplicate", action: "Объясни следующий шаг расчёта", example: "Уточним объём работы", evidence: "Стоимость пока не рассчитана", segment_index: 2, origin: "answer" },
  ],
  criteria: [{ criterion: "Жесты", status: "unknown", reason: "В разборе есть только текст", evidence: "" }],
  metrics: [{ title: "Объём расшифровки", text: "12 слов", label: "Распознанный текст" }],
  limitations: ["Расшифровка может содержать ошибки"],
  transcript_segments: [{ index: 0, kind: "speech", text: "Это кэш" }, { index: 2, kind: "answer", text: "Стоимость пока не рассчитана", question: "Сколько стоит запуск?" }],
};
const practice = { id: "source", created_at: 1728777600, config: { topic: "История", duration: 1, questions: true, criteria: "Мои исходные критерии" }, report, segments: [{ id: "private", kind: "speech", index: 0 }] };
const ui = context.ui;
ui.state.user = { id: "owner", onboarding_completed: true };
ui.state.practice = practice;
ui.reportPage(practice);
assert.match(context.markup, /Фокус следующей попытки/);
assert.match(context.markup, /<h3 class="insight-copy">Ответ<\/h3>/);
assert.match(context.markup, /Ответ на вопрос 2/);
assert.match(context.markup, /Возможная формулировка/);
assert.match(context.markup, /По этой записи нельзя оценить/);
assert.match(context.markup, /В разборе есть только текст/);
assert.match(context.markup, /\/api\/practices\/source\/segments\/private\/media/);
assert.match(context.markup, /value="1" checked/);
assert.equal((context.markup.match(/legacy fallback duplicate/g) || []).length, 0);
assert.equal((context.markup.match(/button primary/g) || []).length, 1, "Only one primary action in the report");
assert.match(context.markup, /<details class="report-detail transcript">/);
assert.ok(context.markup.indexOf("Цена пока неизвестна") < context.markup.indexOf("Текст речи и записи"));
assert.ok(context.markup.indexOf("Объясни следующий шаг расчёта") < context.markup.indexOf("Цена пока неизвестна"), "Main action precedes its rationale on narrow viewports");
assert.ok(context.markup.indexOf("Объясни следующий шаг расчёта") < context.markup.indexOf("Стоимость пока не рассчитана"), "Main action precedes its canonical quote without shortening it");
const firstReading = context.markup.slice(context.markup.indexOf('<section class="report-insight">'), context.markup.indexOf('<section class="report-observations">'));
assert.equal((firstReading.match(/Объясни следующий шаг расчёта/g) || []).length, 1, "Main action is not repeated inside the finding");
const text = ui.reportText(practice);
assert.equal((text.match(/Цена пока неизвестна/g) || []).length, 1, "V2 observation is exported once");
assert.equal((text.match(/Объясни следующий шаг расчёта/g) || []).length, 1, "Primary action is exported once");
assert.doesNotMatch(text, /legacy fallback duplicate/);
for (const expected of ["Ответ на вопрос 2", "Стоимость пока не рассчитана", "Возможная формулировка: Уточним объём работы", "Жесты", "По этой записи нельзя оценить", "В разборе есть только текст", "Сколько стоит запуск?", "12 слов"]) assert.ok(text.includes(expected), expected);
const target = { dataset: { action: "repeat" }, disabled: false, isConnected: true };
await ui.action({ target: { closest: () => target } });
assert.equal(created[0].criteria, practice.config.criteria, "Focus must not overwrite user's original criteria");
assert.equal(created[0].repeat_source_id, "source");
assert.equal(created[0].repeat_recommendation_index, 1);
assert.equal(created[0].repeat_focus, undefined, "Client must not submit arbitrary trusted focus text");

const sparse = { schema_version: 2, primary_recommendation_index: null, insight: "Do not display fabricated insight", strengths: [], recommendations: [], criteria: [] };
const sparseHTML = ui.reportMarkup(sparse);
assert.match(sparseHTML, /Обоснованного фокуса для повтора пока нет/);
assert.match(sparseHTML, /Записать ещё одну попытку/);
assert.doesNotMatch(sparseHTML, /Do not display|Фокус следующей попытки|Твои критерии/);
assert.equal(ui.repeatChoices(sparse).length, 0);
assert.equal(ui.repeatPanel({ report: sparse }), "");
checked = undefined;
ui.state.practice = { ...practice, report: sparse };
await ui.action({ target: { closest: () => target } });
assert.equal(created[1].repeat_recommendation_index, null);
assert.equal(created[1].criteria, practice.config.criteria);
const noPriority = { ...report, primary_recommendation_index: null };
assert.doesNotMatch(ui.repeatPanel({ report: noPriority }), / checked/);
ui.state.practice = { ...practice, report: noPriority };
target.dataset.action = "repeat-selected";
await ui.action({ target: { closest: () => target } });
assert.equal(created.length, 2, "Explicit focused repeat needs an actual selected recommendation");
assert.match(context.notification, /Выбери рекомендацию/);

const legacy = { insight: "Старый главный вывод", strengths: [], recommendations: [{ title: "Старый совет", text: "Сохранённый совет", evidence: "Старая цитата" }], transcript: "Старый текст", criteria: [{ criterion: "Тема", status: "partial", evidence: "Старая цитата" }] };
assert.match(ui.reportMarkup(legacy), /Старый главный вывод/);
const legacyText = ui.reportText({ ...practice, report: legacy });
for (const expected of ["Старый главный вывод", "Старая цитата", "Старый текст", "Сохранённый совет", "Частично"]) assert.ok(legacyText.includes(expected), expected);
assert.match(ui.reportMarkup({ ...legacy, recommendations: [{ ...legacy.recommendations[0], segment_index: null }] }), /Фрагмент записи/);
const legacyMissing = { ...legacy, criteria: [{ criterion: "Бюджет", status: "not_met", evidence: "Старая цитата" }] };
assert.match(ui.reportMarkup(legacyMissing), /Не найдено в тексте речи/, "Legacy absence status keeps its meaning");
const observedContradiction = { ...report, criteria: [{ criterion: "Назвать цену", status: "not_met", basis: "present", reason: "Стоимость ещё не рассчитана", evidence: "Стоимость пока не рассчитана", origin: "answer", segment_index: 2 }] };
assert.match(ui.reportMarkup(observedContradiction), /Есть несоответствие критерию/);
// Provider-supplied markup must remain escaped in every report path, including examples and questions.
const attack = '<img src=x onerror="steal()">';
const malicious = { ...report, recommendations: [{ ...report.recommendations[0], title: attack, observation: attack, action: attack, example: attack, evidence: attack }], primary_recommendation_index: 0, transcript_segments: [{ kind: "answer", index: 1, text: attack, question: attack }] };
ui.reportPage({ ...practice, report: malicious });
assert.doesNotMatch(context.markup, /<img|onerror="steal/);
assert.match(context.markup, /&lt;img/);
console.log("Report focus, source, export, empty/legacy states, escaping and selected repeat checks passed");

ui.processingPage(practice, {id:"pending-report",kind:"report",stage:"transcription_1"});
assert.equal((context.markup.match(/Готовим разбор выступления/g) || []).length,1);
assert.match(context.markup,/id="job-status" role="status">Можно закрыть страницу/);
assert.doesNotMatch(context.markup,/транскрип|расшифров|сервер|очеред/);
console.log("Processing screen has one title and useful continuation copy");

const oldPractice = {...practice,report:{...report,provenance:{report_prompt_version:"speech-feedback-v2.2"}}};
ui.state.practice = oldPractice;
ui.reportPage(oldPractice);
assert.match(context.markup,/data-action="refresh-report"/);
const calls=[];
context.api.startJob=async(...args)=>{calls.push(args);return {id:"refresh-job",kind:"report"};};
const refreshButton={dataset:{action:"refresh-report"},disabled:false,isConnected:true};
await ui.action({target:{closest:()=>refreshButton}});
assert.equal(calls[0][0],"source");
assert.equal(calls[0][1],"report");
assert.equal(calls[0][2].refresh,true);
assert.equal(oldPractice.report.provenance.report_prompt_version,"speech-feedback-v2.2");
ui.reportPage({...practice,report:{...report,provenance:{report_prompt_version:"speech-feedback-v2.3"}}});
assert.doesNotMatch(context.markup,/data-action="refresh-report"/);
console.log("Old reports offer explicit update; current reports remain idempotent");
