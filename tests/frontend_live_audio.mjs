import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { PCMChunker, pcmWav, LiveAudioCapture } from "../public/live-audio.js";

// Frame boundaries must not change resampling or independently decodable files.
for (const inputRate of [44100, 48000, 16000]) {
  const chunks = [];
  const chunker = new PCMChunker(inputRate, 16000, 1, (samples, offset) =>
    chunks.push({ samples, offset }),
  );
  const source = Float32Array.from(
    { length: Math.round(inputRate * 2.37) },
    (_, i) => 0.6 * Math.sin((i * 2 * Math.PI * 440) / inputRate),
  );
  for (let start = 0; start < source.length; start += 128) {
    const channel = source.subarray(start, start + 128);
    chunker.push([channel, channel]);
  }
  chunker.flush();
  assert.equal(chunks.length, 3);
  assert.equal(chunks[0].offset, 0);
  assert.equal(chunks[1].offset, 1);
  assert.equal(chunks[2].offset, 2);
  assert.ok(
    Math.abs(
      chunks.reduce((sum, chunk) => sum + chunk.samples.length, 0) - 37920,
    ) <= 1,
  );
  for (const { samples } of chunks) {
    const bytes = await pcmWav(samples).arrayBuffer();
    const view = new DataView(bytes);
    assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), "RIFF");
    assert.equal(new TextDecoder().decode(bytes.slice(8, 12)), "WAVE");
    assert.equal(view.getUint16(22, true), 1);
    assert.equal(view.getUint32(24, true), 16000);
    assert.equal(view.getUint16(34, true), 16);
    assert.equal(view.getUint32(40, true), samples.length * 2);
    assert.ok(
      Math.abs(view.getInt16(44 + 30 * 2, true) / 32767 - samples[30]) <
        0.00004,
    );
  }
}
{
  const bytes = new DataView(
    await pcmWav(new Float32Array([-2, -1, 0, 1, 2])).arrayBuffer(),
  );
  assert.deepEqual(
    Array.from({ length: 5 }, (_, i) => bytes.getInt16(44 + i * 2, true)),
    [-32768, -32768, 0, 32767, 32767],
  );
}
{
  let Processor;
  const messages = [];
  const worklet = vm.createContext({
    PCMChunker,
    sampleRate: 48000,
    AudioWorkletProcessor: class {
      constructor() {
        this.port = { postMessage: (message) => messages.push(message) };
      }
    },
    registerProcessor(name, processor) {
      assert.equal(name, "speech-pcm-capture");
      Processor = processor;
    },
  });
  vm.runInContext(
    readFileSync(
      new URL("../public/audio-capture-worklet.js", import.meta.url),
      "utf8",
    ).replace(/^import.*;\n/, ""),
    worklet,
  );
  const processor = new Processor();
  processor.process([[new Float32Array(48000).fill(0.25)]]);
  assert.equal(messages.length, 0); // Device preparation does not upload pre-recording audio.
  processor.port.onmessage({ data: { type: "start" } });
  processor.process([[new Float32Array(48000 * 4).fill(0.25), new Float32Array(48000 * 4).fill(0.75)]]);
  assert.equal(messages.length, 0, "No upload before five seconds");
  processor.process([[new Float32Array(48000).fill(0.25), new Float32Array(48000).fill(0.75)]]);
  assert.equal(messages.length, 1, "First full chunk arrives at five seconds");
  processor.process([[new Float32Array(48000 * 5).fill(0.5)]]);
  assert.equal(messages.length, 2);
  processor.process([[new Float32Array(48000).fill(0.5)]]);
  processor.port.onmessage({ data: { type: "flush" } });
  assert.equal(messages[0].samples.length, 80000);
  assert.equal(messages[0].samples[0], 0.5);
  assert.equal(messages[0].offset, 0);
  assert.equal(messages[1].offset, 5);
  assert.equal(messages[2].offset, 10);
  assert.equal(messages[2].samples.length, 16000);
  assert.equal(messages[3].type, "flushed");
  processor.process([[new Float32Array(48000)]]);
  assert.equal(messages.length, 4);
}
function fixture({ fail = false } = {}) {
  const uploaded = [],
    messages = [],
    status = [];
  const capture = new LiveAudioCapture({
    context: {},
    stream: {},
    practiceId: "private-practice",
    onStatus: (value) => status.push(value),
    api: {
      async liveChunk(id, blob, sessionId, index, offset) {
        uploaded.push({ id, blob, sessionId, index, offset });
        if (fail) throw new Error("Offline");
      },
      async liveTranscript() {
        return { status: "ready", recognized_words: 17 };
      },
    },
  });
  capture.node = {
    port: {
      postMessage(message) {
        messages.push(message);
        if (message.type === "flush") {
          capture.enqueue(new Float32Array(3200), 5);
          capture.resolveFlush();
        }
      },
    },
    disconnect() {},
  };
  capture.source = { disconnect() {} };
  capture.silent = { disconnect() {} };
  return { capture, uploaded, messages, status };
}
{
  const f = fixture();
  assert.equal(f.capture.start(), true);
  f.capture.enqueue(new Float32Array(80000), 0);
  await f.capture.chain;
  await f.capture.poll();
  assert.equal(f.status.at(-1).recognized_words, 17);
  const completed = await f.capture.finish();
  assert.equal(completed.sessionId, f.capture.sessionId);
  assert.equal(completed.chunkCount, 2);
  assert.deepEqual(
    f.uploaded.map((upload) => [upload.index, upload.offset]),
    [
      [0, 0],
      [1, 5],
    ],
  );
  assert.equal(f.capture.cancelled, true);
  assert.equal(f.capture.abortController.signal.aborted, true);
}
{
  const f = fixture({ fail: true });
  f.capture.start();
  f.capture.enqueue(new Float32Array(80000), 0);
  await f.capture.chain;
  assert.equal(f.capture.failed, true);
  assert.equal(await f.capture.finish(), null);
  assert.equal(f.status.at(-1).status, "unavailable");
}
{
  const f = fixture();
  f.capture.start();
  for (let i = 0; i < 5; i++) f.capture.enqueue(new Float32Array(16), i / 1000);
  assert.equal(f.capture.failed, true);
  await f.capture.chain;
  assert.equal(f.uploaded.length, 0);
  f.capture.cancel();
}
{
  const f = fixture();
  f.capture.start();
  f.capture.enqueue(new Float32Array(16), 0);
  f.capture.cancel();
  await f.capture.chain;
  assert.equal(f.uploaded.length, 0);
  assert.equal(await f.capture.finish(), null);
}
{
  const f = fixture();
  f.capture.start();
  f.capture.node.port.postMessage = () => {};
  f.capture.bounded = async () => false;
  assert.equal(await f.capture.finish(), null);
}
console.log(
  "PCM WAV, sample rate conversion, ordered uploads, final flush and fallback cases passed",
);

// Reuse the existing full-recording harness and exercise the extra manifest,
// without opening a real microphone or replacing the meeting DOM.
const harness = readFileSync(
  new URL("./frontend_autosave.mjs", import.meta.url),
  "utf8",
)
  .replace(/^import.*;\n/gm, "")
  .replace(
    /const source = readFileSync\([\s\S]*?\.split\('app\.addEventListener\("submit"'\)\[0\];/,
    "const source = applicationSource;",
  )
  .split("for (const automatic")[0]
  .replace("    flow,\n    events,", "    flow,\n    api,\n    events,");
const applicationSource = readFileSync(
  new URL("../public/app.js", import.meta.url),
  "utf8",
)
  .replace(/^import[\s\S]*?;\n/gm, "")
  .split('app.addEventListener("submit"')[0];
const harnessContext = vm.createContext({
  applicationSource,
  assert,
  vm,
  Blob,
  console,
  randomUUID: () => crypto.randomUUID(),
});
vm.runInContext(harness, harnessContext);
for (const stale of [false, true]) {
  const f = harnessContext.fixture();
  const uploads = [];
  f.flow.state.user = { id: "account" };
  f.flow.state.liveCapture = {
    context: {},
    start: () => true,
    finish: async () => ({ sessionId: "b".repeat(32), chunkCount: 4 }),
  };
  f.api.upload = async (_id, blob, kind, index, sessionId, chunkCount) => {
    uploads.push({ blob, sessionId, chunkCount });
    if (stale && sessionId)
      throw Object.assign(new Error("Expired live session"), {
        code: "LIVE_SESSION_STALE",
      });
    return { id: "saved", kind, index, media_url: "/media" };
  };
  f.flow.startRecording();
  f.flow.stopRecording();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(uploads[0].sessionId, "b".repeat(32));
  assert.equal(uploads[0].chunkCount, 4);
  assert.equal(uploads.length, stale ? 2 : 1);
  if (stale) assert.equal(uploads[1].sessionId, undefined);
  assert.equal(f.flow.state.pending, null);
  assert.equal(f.flow.state.practice.segments.length, 1);
  assert.equal(f.events.filter((event) => event.type === "job").length, 1);
  assert.equal(
    f.events.some((event) => event.type === "frame"),
    false,
  );
}
console.log(
  "Authenticated autosave manifest and stale-cache fallback cases passed",
);
