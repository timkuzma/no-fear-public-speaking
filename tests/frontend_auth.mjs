import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { api } from "../public/api.js";
import { loadDraft } from "../public/guest-draft.js";

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
  await assert.rejects(api.me(), /Сервер не успел ответить/);
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
  globalThis.flow = { state, submitForm, startLink, navigate };
`, context);
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(context.location.hash, "/app");
assert.equal(context.flow.state.user.id, "test-user");
assert.equal(submit.disabled, false);
assert.equal(attributes.has("aria-busy"), false);
assert.match(events[0], /Аккаунт создан/);

context.flow.state.user = null;
context.location.hash = "#/register";
mockedApi.register = async () => { throw new Error("Нет связи с сервером"); };
await context.flow.submitForm({ target: form, preventDefault() {} });
assert.equal(error.textContent, "Нет связи с сервером");
assert.equal(submit.disabled, false);
assert.equal(submit.textContent, "Регистрация");
assert.equal(values.email, " synthetic@example.test ", "Failed registration must retain form values");
assert.match(context.flow.startLink(), /href="#\/register"/);
context.location.hash = "#/guest";
await context.flow.navigate();
assert.equal(context.location.hash, "/register");
console.log("Auth completion, timeout recovery, storage bounds and anonymous entry checks passed");
