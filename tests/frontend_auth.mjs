import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { api } from "../public/api.js";
import { loadDraft, loadRecordingDrafts } from "../public/guest-draft.js";

const nativeTimer = globalThis.setTimeout;
const nativeFetch = globalThis.fetch;
const timeoutValues = [];
globalThis.setTimeout = (callback, delay) => {
  timeoutValues.push(delay);
  return nativeTimer(callback, 20);
};
try {
  globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) =>
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))));
  await assert.rejects(api.register({ email: "synthetic@example.test" }), (error) =>
    error.status === 0 && /аккаунт мог уже создаться/.test(error.message));
  assert.equal(timeoutValues.shift(), 15000);
  await assert.rejects(api.me(), /Ответ не пришёл вовремя/);
  assert.equal(timeoutValues.shift(), 10000);

  let opening;
  globalThis.indexedDB = { open: () => (opening = {}) };
  await assert.rejects(loadDraft(), /Хранилище записи не ответило/);
  assert.equal(timeoutValues.shift(), 5000);
  let closed = 0;
  opening.result = { close: () => closed++ };
  opening.onsuccess();
  assert.equal(closed, 1, "A late database open must not leak a connection");

  let aborted = 0;
  const transaction = {
    objectStore: () => ({ get: () => ({ result: null }) }),
    abort: () => aborted++,
  };
  globalThis.indexedDB.open = () => {
    const request = { result: { transaction: () => transaction, close: () => closed++ } };
    nativeTimer(() => request.onsuccess(), 0);
    return request;
  };
  await assert.rejects(loadDraft(), /Хранилище записи не ответило/);
  assert.equal(aborted, 1);
  assert.equal(closed, 2);
} finally {
  globalThis.setTimeout = nativeTimer;
  globalThis.fetch = nativeFetch;
}

{
  const previousDB = globalThis.indexedDB, previousRange = globalThis.IDBKeyRange;
  const draft = {ownerId:"owner",createdAt:Date.now(),blob:new Blob(["bytes"])};
  globalThis.IDBKeyRange = {bound:(first,last)=>{
    assert.equal(first,"account:owner:");
    assert.equal(last,"account:owner:\uffff");
    return {};
  }};
  globalThis.indexedDB = {open:()=>{
    const opening = {result:{close(){},transaction(_store,mode){
      assert.equal(mode,"readonly");
      const tx={objectStore:()=>({
        getAll:()=>{
          const result={result:[draft,{...draft,createdAt:Date.now()-86400001},{...draft,ownerId:"other"}]};
          queueMicrotask(()=>tx.oncomplete());
          return result;
        },
        delete(){assert.fail("Copy recovery must never delete a draft")},
      })};
      return tx;
    }}};
    queueMicrotask(()=>opening.onsuccess());
    return opening;
  }};
  try {
    assert.deepEqual(await loadRecordingDrafts("owner",{pruneExpired:false}),[draft]);
  } finally {
    globalThis.indexedDB=previousDB;globalThis.IDBKeyRange=previousRange;
  }
}

const source = readFileSync(new URL("../public/app.js", import.meta.url), "utf8")
  .replace(/^import[\s\S]*?;\n/gm, "")
  .split('app.addEventListener("submit"')[0];
const events = [];
const values = { email: " synthetic@example.test ", password: "SyntheticPassword2026", name: " Проверка ", role: "other" };
const submit = { textContent: "Регистрация", disabled: false };
const error = { textContent: "" };
const attributes = new Map();
const form = {
  id: "auth-form", dataset: { mode: "register" }, isConnected: true,
  matches: () => true,
  querySelector: (selector) => selector === "[type=submit]" ? submit : error,
  setAttribute: (key, value) => attributes.set(key, value),
  removeAttribute: (key) => attributes.delete(key),
};
const mockedApi = {
  register: async (body) => {
    assert.equal("consent" in body, false);
    assert.equal(body.email, "synthetic@example.test");
    return { user: { id: "test-user" }, provider_ready: true, registration_requires_invite: false };
  },
  me: () => { throw new Error("Registration must not wait for a redundant session request"); },
};
const context = vm.createContext({
  document: { querySelector: () => ({}) },
  location: { hash: "#/register" }, window: { scrollTo() {} },
  sessionStorage: { removeItem() {} },
  api: mockedApi, loadDraft: async () => null, clearTimeout,
  FormData: class { [Symbol.iterator]() { return Object.entries(values)[Symbol.iterator](); } },
  events,
});
vm.runInContext(source + `
  frame = content => events.push(content);
  closeMedia = () => {};
  globalThis.flow = { state, submitForm, startLink, navigate, action, setupForm, errorText };
`, context);
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(context.location.hash, "/app");
assert.equal(context.flow.state.user.id, "test-user");
assert.equal(submit.disabled, false);
assert.equal(attributes.has("aria-busy"), false);
assert.match(events[0], /Аккаунт создан/);

context.flow.state.user = null;
context.location.hash = "#/register";
mockedApi.register = async () => { throw new Error("Не удалось подключиться"); };
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(error.textContent, "Не удалось подключиться");
assert.equal(submit.disabled, false);
assert.equal(submit.textContent, "Регистрация");
assert.equal(values.email, " synthetic@example.test ", "Failed registration must retain form values");
assert.match(context.flow.startLink(), /href="#\/register"/);
context.location.hash = "#/guest";
await context.flow.navigate();
assert.equal(context.location.hash, "/register");
// Starting practice must not silently set a speech task or assessment rubric.
context.flow.state.user = { id: "test-user" };
const createdConfigs = [];
mockedApi.createPractice = async (config) => {
  createdConfigs.push(JSON.parse(JSON.stringify(config)));
  return { id: "neutral-practice" };
};
const starter = { dataset: { action: "starter" }, disabled: false, isConnected: true };
await context.flow.action({ target: { closest: () => starter } });
assert.equal(context.location.hash, "/practice/neutral-practice");
assert.deepEqual(createdConfigs[0], { scenario: "speech", topic: "", duration: 1, questions: true, criteria: "" });
assert.equal(starter.disabled, false);
form.id = "setup-form";
Object.assign(values, { scenario: "free", topic: "", minutes: "3", seconds: "20", questions: "on", criteria: "" });
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(createdConfigs.length, 2, "Custom practice may start without a topic or criteria");
assert.deepEqual(createdConfigs[1], { scenario: "free", topic: "", duration: 200 / 60, questions: true, criteria: "" });
Object.assign(values, { topic: "Моя история", criteria: "Понятен ли рассказ" });
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(createdConfigs[2].topic, "Моя история");
assert.equal(createdConfigs[2].criteria, "Понятен ли рассказ", "Explicit user criteria must remain available");
const visibleForm = context.flow.setupForm(false);
assert.ok(visibleForm.indexOf('name="topic"') < visibleForm.indexOf('<details'));
assert.ok(visibleForm.indexOf('name="minutes"') < visibleForm.indexOf('<details'));
assert.ok(visibleForm.indexOf('name="seconds"') < visibleForm.indexOf('<details'));
assert.match(visibleForm, /type="number" name="minutes" min="0" max="10" step="1"/);
assert.match(visibleForm, /type="number" name="seconds" min="0" max="59" step="1"/);
for (const [minutes, seconds, totalSeconds] of [["0", "30", 30], ["10", "0", 600], ["1", "1", 61]]) {
  Object.assign(values, { minutes, seconds });
  await context.flow.submitForm({ target: form, preventDefault() {} });
  assert.equal(createdConfigs.at(-1).duration, totalSeconds / 60);
}
for (const [minutes, seconds] of [["0", "29"], ["10", "1"], ["3", "60"], ["1.5", "0"], ["3", "0.5"], ["", "30"], ["0", ""], ["-1", "30"], ["11", "0"]]) {
  const count = createdConfigs.length;
  Object.assign(values, { minutes, seconds });
  await context.flow.submitForm({ target: form, preventDefault() {} });
  assert.equal(createdConfigs.length, count, "Invalid combined time must not create a practice");
  assert.match(error.textContent, /Укажи/);
  assert.equal(values.minutes, minutes);
  assert.equal(values.seconds, seconds);
  assert.equal(submit.disabled, false);
}
assert.doesNotMatch(context.flow.errorText({code:"STORAGE_CAPACITY",message:"На сервере недостаточно места"}), /сервер/);
assert.doesNotMatch(context.flow.errorText({message:"Не удалось прочитать идентификатор записи"}), /идентификатор/);
console.log("Auth completion, timeout recovery, storage bounds and anonymous entry checks passed");
