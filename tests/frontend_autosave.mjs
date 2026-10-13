import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import vm from "node:vm";

const source = readFileSync(
  new URL("../public/app.js", import.meta.url),
  "utf8",
)
  .replace(/^import[\s\S]*?;\n/gm, "")
  .split('app.addEventListener("submit"')[0];

function fixture({
  guest = false,
  answer = false,
  failUpload = false,
  accountDrafts = new Map(),
  storageFails = false,
} = {}) {
  const events = [],
    drafts = [],
    nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: "",
        textContent: "",
        hidden: false,
        setAttribute() {},
        insertAdjacentHTML(_position, content) {
          this.innerHTML += content;
        },
        closest() {
          return this;
        },
      });
    return nodes.get(selector);
  };
  let timer;
  let clockOffset = 0;
  let rejectUpload = failUpload;
  const session = new Map();
  const api = {
    async upload(id, blob, kind, index, _sessionId, _chunkCount, clientKey) {
      events.push({ type: "upload", id, blob, kind, index, clientKey });
      if (rejectUpload)
        throw Object.assign(new Error("Connection failed"), { status: 0 });
      return { id: "saved", kind, index, media_url: "/media" };
    },
    async startJob(id, kind) {
      events.push({ type: "job", id, kind });
      return { id: "job", kind, stage: "queued" };
    },
  };
  class Recorder {
    static isTypeSupported() {
      return true;
    }
    constructor() {
      this.mimeType = "audio/webm";
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable({
        data: new Blob(["captured audio"], { type: this.mimeType }),
      });
      this.onstop();
    }
  }
  const track = {
    readyState: "live",
    enabled: true,
    stop() {
      this.readyState = "ended";
    },
  };
  const context = vm.createContext({
    api,
    events,
    drafts,
    Blob,
    crypto: { randomUUID },
    Date: class extends Date {
      static now() {
        return Date.now() + clockOffset;
      }
    },
    MediaRecorder: Recorder,
    MediaStream: class {},
    console,
    URL: { createObjectURL: () => "blob:recording", revokeObjectURL() {} },
    document: { querySelector: node },
    location: { hash: "#/practice/practice" },
    window: { scrollTo() {}, history: { replaceState() {} } },
    sessionStorage: {
      setItem: (key, value) => session.set(key, value),
      getItem: (key) => session.get(key),
      removeItem: (key) => session.delete(key),
    },
    confirm: () => true,
    setInterval(callback) {
      timer = callback;
      return 1;
    },
    clearInterval() {},
    setTimeout() {
      return 1;
    },
    clearTimeout() {},
    cancelAnimationFrame() {},
    saveDraft: async (draft) => drafts.push(draft),
    clearDraft: async () => {},
    loadDraft: async () => null,
    saveRecordingDraft: async (draft) => {
      if (storageFails) throw new Error("Storage denied");
      accountDrafts.set(
        `${draft.ownerId}:${draft.practiceId}:${draft.index}`,
        structuredClone(draft),
      );
    },
    loadRecordingDrafts: async (ownerId) =>
      [...accountDrafts.values()].filter((d) => d.ownerId === ownerId),
    clearRecordingDraft: async (draft) => {
      const key = `${draft.ownerId}:${draft.practiceId}:${draft.index}`;
      if (accountDrafts.get(key)?.clientKey === draft.clientKey)
        accountDrafts.delete(key);
    },
  });
  vm.runInContext(
    source +
      `
    meetingPage = p => events.push({type:'meeting', id:p.id, uploading:state.uploading});
    frame = content => events.push({type:'frame', content});
    globalThis.flow = {state, startRecording, stopRecording, saveRecording, questionChat, restorePending, sessionExpired, resumeAfterLogin, navigate, continueAfterSave, showPending, action};
  `,
    context,
  );
  const flow = context.flow;
  flow.state.user = guest
    ? null
    : { id: "account", onboarding_completed: true };
  flow.state.practice = {
    id: guest ? "guest" : "practice",
    config: { duration: 1, questions: true, topic: "Fixture" },
    segments: answer
      ? [{ kind: "speech", index: 0, duration_seconds: 10 }]
      : [],
    questions: answer
      ? ["Question one?", "Question two?", "Question three?"]
      : [],
  };
  flow.state.stream = {
    getTracks: () => [track],
    getAudioTracks: () => [track],
  };
  flow.state.providerReady = true;
  return {
    flow,
    events,
    drafts,
    accountDrafts,
    api,
    context,
    advance(milliseconds) {
      clockOffset += milliseconds;
    },
    node,
    allowUpload() {
      rejectUpload = false;
    },
    expire() {
      flow.state.started = Date.now() - 61000;
      timer();
    },
  };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

for (const automatic of [false, true]) {
  const f = fixture();
  f.flow.startRecording();
  if (automatic) f.expire();
  else f.flow.stopRecording();
  await settle();
  assert.equal(f.events.filter((e) => e.type === "upload").length, 1);
  assert.equal(f.events.find((e) => e.type === "upload").blob.size, 14);
  assert.equal(f.events.find((e) => e.type === "job").kind, "questions");
  assert.equal(f.flow.state.pending, null);
  assert.equal(f.flow.state.practice.segments.length, 1);
  assert.equal(
    f.events.some((e) => e.type === "frame"),
    false,
  );
}
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  assert.equal(f.flow.state.pending.blob.size, 14);
  assert.equal(f.flow.state.uploading, false);
  assert.equal(
    f.events.some((e) => e.type === "job"),
    false,
  );
  assert.match(
    f.flow.questionChat(f.flow.state.practice, null, null),
    /Повторить сохранение/,
  );
  assert.equal(
    f.events.some((e) => e.type === "frame"),
    false,
  );
  f.allowUpload();
  await f.flow.saveRecording();
  assert.equal(f.events.filter((e) => e.type === "upload").length, 2);
  assert.equal(f.events.filter((e) => e.type === "job").length, 1);
  assert.equal(f.flow.state.practice.segments.length, 1);
  assert.equal(f.flow.state.pending, null);
}
{
  const f = fixture({ guest: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  assert.equal(f.drafts.length, 1);
  assert.equal(f.drafts[0].blob.size, 14);
  assert.equal(f.flow.state.guestPersisted, true);
  assert.equal(f.flow.state.pending, null);
  assert.equal(
    f.events.some((e) => e.type === "upload" || e.type === "job"),
    false,
  );
  assert.equal(
    f.events.some((e) => e.type === "frame"),
    false,
  );
  assert.match(
    f.flow.questionChat(f.flow.state.guest, null, null),
    /Создать аккаунт и продолжить/,
  );
}
{
  const f = fixture({ answer: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  assert.equal(f.flow.state.pending.kind, "answer");
  assert.equal(
    f.events.some((e) => e.type === "upload"),
    false,
  );
  assert.match(
    f.events.find((e) => e.type === "frame").content,
    /record-review/,
  );
}
console.log("5 recording lifecycle cases passed");

// Reload must use the same account, stage, bytes and upload key.
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  const original = f.flow.state.pending;
  assert.equal(f.accountDrafts.size, 1);
  const restored = fixture({ accountDrafts: f.accountDrafts });
  await restored.flow.restorePending(restored.flow.state.practice);
  assert.equal(
    await restored.flow.state.pending.blob.text(),
    await original.blob.text(),
  );
  assert.equal(restored.flow.state.pending.clientKey, original.clientKey);
  assert.equal(restored.flow.state.pendingPersisted, true);
  await restored.flow.saveRecording();
  assert.equal(
    restored.events.find((e) => e.type === "upload").clientKey,
    original.clientKey,
  );
  assert.equal(f.accountDrafts.size, 0);
}
{
  const f = fixture({ answer: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  const restored = fixture({ answer: true, accountDrafts: f.accountDrafts });
  await restored.flow.restorePending(restored.flow.state.practice);
  assert.equal(restored.flow.state.pending.kind, "answer");
  assert.equal(restored.flow.state.pending.autoSave, false);
  assert.equal(restored.events.filter((e) => e.type === "upload").length, 0);
  await restored.flow.saveRecording();
  assert.equal(restored.events.find((e) => e.type === "upload").index, 1);
  assert.equal(f.accountDrafts.size, 0);
}
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  f.flow.sessionExpired();
  assert.equal(f.flow.state.user, null);
  assert.equal(f.flow.state.authReturn.ownerId, "account");
  assert.match(
    f.flow.questionChat(f.flow.state.practice, null, null),
    /Войти и продолжить/,
  );
  const serverPractice = structuredClone(f.flow.state.practice);
  f.api.practice = async () => serverPractice;
  f.allowUpload();
  f.flow.state.user = { id: "account", onboarding_completed: true };
  await f.flow.resumeAfterLogin();
  await settle();
  assert.equal(f.flow.state.pending, null);
  assert.equal(f.accountDrafts.size, 0);
  assert.equal(f.events.filter((e) => e.type === "job").length, 1);
}
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  f.flow.sessionExpired();
  f.flow.state.user = { id: "another-account", onboarding_completed: true };
  await f.flow.resumeAfterLogin();
  assert.equal(f.flow.state.pending, null);
  assert.equal(f.context.location.hash, "/app");
  assert.equal(f.accountDrafts.size, 1);
  assert.equal(f.events.filter((e) => e.type === "upload").length, 1);
}
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  const restored = fixture({ accountDrafts: f.accountDrafts });
  restored.flow.state.practice.segments.push({
    id: "server",
    kind: "speech",
    index: 0,
    client_key: f.flow.state.pending.clientKey,
  });
  assert.equal(
    await restored.flow.restorePending(restored.flow.state.practice),
    true,
  );
  assert.equal(restored.flow.state.pending, null);
  assert.equal(f.accountDrafts.size, 0);
  assert.equal(restored.events.filter((e) => e.type === "upload").length, 0);
}
{
  const f = fixture({ failUpload: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  const restored = fixture({ accountDrafts: f.accountDrafts });
  restored.flow.state.practice.segments.push({
    id: "different",
    kind: "speech",
    index: 0,
    client_key: "different-recording",
  });
  await restored.flow.restorePending(restored.flow.state.practice);
  assert.equal(restored.flow.state.pending.conflict, true);
  restored.flow.showPending();
  assert.match(restored.events.at(-1).content, /Скачать черновик/);
  assert.equal(f.accountDrafts.size, 1);
}
{
  const f = fixture({ failUpload: true, storageFails: true });
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  assert.equal(f.flow.state.pendingPersisted, false);
  assert.equal(f.flow.state.pending.blob.size, 14);
  assert.match(
    f.flow.questionChat(f.flow.state.practice, null, null),
    /Не закрывай/,
  );
}
{
  const f = fixture();
  f.flow.startRecording();
  f.advance(6000);
  f.flow.state.recorder.ondataavailable({
    data: new Blob(["first fragment"], { type: "audio/webm" }),
  });
  await settle();
  const restored = fixture({ accountDrafts: f.accountDrafts });
  await restored.flow.restorePending(restored.flow.state.practice);
  assert.equal(restored.flow.state.pending.interrupted, true);
  assert.equal(restored.flow.state.pending.autoSave, false);
  assert.equal(await restored.flow.state.pending.blob.text(), "first fragment");
  assert.equal(restored.events.filter((e) => e.type === "upload").length, 0);
}
console.log("8 draft recovery, reauthentication and isolation cases passed");
{
  const f = fixture();
  f.flow.startRecording();
  f.advance(6000);
  f.flow.state.recorder.ondataavailable({
    data: new Blob(["recoverable fragment"], { type: "audio/webm" }),
  });
  await settle();
  const restored = fixture({
    accountDrafts: f.accountDrafts,
    failUpload: true,
  });
  await restored.flow.restorePending(restored.flow.state.practice);
  assert.equal(restored.flow.state.pending.interrupted, true);
  await restored.flow.saveRecording();
  assert.equal(restored.flow.state.pending.interrupted, false);
  assert.equal([...f.accountDrafts.values()][0].autoSave, true);
  assert.equal([...f.accountDrafts.values()][0].interrupted, false);
  assert.equal(
    await [...f.accountDrafts.values()][0].blob.text(),
    "recoverable fragment",
  );
}
console.log(
  "Confirmed interrupted fragments can resume the same upload after failure",
);
{
  const f = fixture();
  f.flow.state.guest = {
    ownerId: "account",
    serverPracticeId: "practice",
    clientKey: "a".repeat(32),
    blob: new Blob(["bound guest"], { type: "audio/webm" }),
    config: f.flow.state.practice.config,
    createdAt: Date.now(),
    durationSeconds: 1,
    segments: [{ media_url: "blob:guest" }],
  };
  // The guest copy remains usable even if browser quota prevented a second account copy.
  await f.flow.restorePending(f.flow.state.practice);
  assert.equal(f.flow.state.pending.ownerId, "account");
  assert.equal(await f.flow.state.pending.blob.text(), "bound guest");
  await f.flow.saveRecording();
  assert.equal(f.flow.state.guest, null);
  assert.equal(f.flow.state.pending, null);
}
{
  const f = fixture();
  f.api.startJob = async () => {
    throw new Error("Job admission failed");
  };
  f.flow.startRecording();
  f.flow.stopRecording();
  await settle();
  assert.equal(f.flow.state.pending, null);
  assert.equal(f.flow.state.practice.segments.length, 1);
  assert.equal(f.accountDrafts.size, 0);
  assert.match(f.node(".chat-next").innerHTML, /Запись сохранена/);
  assert.match(
    f.flow.questionChat(f.flow.state.practice, null, null),
    /Подготовить вопросы/,
  );
}
console.log(
  "Bound guest fallback and saved-recording job continuation cases passed",
);
