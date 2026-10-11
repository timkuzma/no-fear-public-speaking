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

function fixture({ guest = false, answer = false, failUpload = false } = {}) {
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
        closest() {
          return this;
        },
      });
    return nodes.get(selector);
  };
  let timer;
  let rejectUpload = failUpload;
  const api = {
    async upload(id, blob, kind, index) {
      events.push({ type: "upload", id, blob, kind, index });
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
    MediaRecorder: Recorder,
    MediaStream: class {},
    console,
    URL: { createObjectURL: () => "blob:recording", revokeObjectURL() {} },
    document: { querySelector: node },
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
  });
  vm.runInContext(
    source +
      `
    meetingPage = p => events.push({type:'meeting', id:p.id, uploading:state.uploading});
    frame = content => events.push({type:'frame', content});
    globalThis.flow = {state, startRecording, stopRecording, saveRecording, questionChat};
  `,
    context,
  );
  const flow = context.flow;
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
