// Independent PCM chunks complement, but never replace, the complete recording.
export class PCMChunker {
  constructor(
    inputRate,
    outputRate = 16000,
    chunkSeconds = 5,
    emit = () => {},
  ) {
    if (!(inputRate > 0 && outputRate > 0 && chunkSeconds > 0))
      throw new Error("Invalid PCM capture configuration");
    this.outputRate = outputRate;
    this.ratio = inputRate / outputRate;
    this.capacity = Math.round(outputRate * chunkSeconds);
    this.emit = emit;
    this.reset();
  }
  reset() {
    this.buffer = new Float32Array(this.capacity);
    this.length = 0;
    this.weight = 0;
    this.sum = 0;
    this.samples = 0;
  }
  push(channels) {
    if (!channels.length) return;
    for (let i = 0; i < channels[0].length; i += 1) {
      let value = 0;
      for (const channel of channels) value += channel[i] / channels.length;
      let remaining = 1;
      while (remaining > 1e-9) {
        const take = Math.min(remaining, this.ratio - this.weight);
        this.sum += value * take;
        this.weight += take;
        remaining -= take;
        if (this.weight >= this.ratio - 1e-9) {
          this.append(this.sum / this.weight);
          this.weight = 0;
          this.sum = 0;
        }
      }
    }
  }
  append(value) {
    this.buffer[this.length++] = value;
    if (this.length === this.capacity) this.flushBuffer();
  }
  flushBuffer() {
    if (!this.length) return;
    const samples = this.buffer.slice(0, this.length);
    const offset = this.samples / this.outputRate;
    this.samples += this.length;
    this.length = 0;
    this.emit(samples, offset);
  }
  flush() {
    if (this.weight > 1e-9) this.append(this.sum / this.weight);
    this.weight = 0;
    this.sum = 0;
    this.flushBuffer();
  }
}
export function pcmWav(samples) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, value) => {
    for (let i = 0; i < value.length; i++)
      view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, index) => {
    const value = Math.max(-1, Math.min(1, sample));
    view.setInt16(
      44 + index * 2,
      Math.round(value * (value < 0 ? 32768 : 32767)),
      true,
    );
  });
  return new Blob([buffer], { type: "audio/wav" });
}

export class LiveAudioCapture {
  constructor({ context, stream, api, practiceId, onStatus = () => {} }) {
    Object.assign(this, { context, stream, api, practiceId, onStatus });
    this.sessionId = crypto.randomUUID().replaceAll("-", "");
    this.abortController = new AbortController();
    this.chain = Promise.resolve();
    this.accepting = false;
    this.failed = false;
    this.cancelled = false;
    this.queued = 0;
    this.count = 0;
  }
  async prepare() {
    if (!this.context.audioWorklet || typeof AudioWorkletNode === "undefined")
      throw new Error("AudioWorklet unavailable");
    await this.context.audioWorklet.addModule(
      "/audio-capture-worklet.js?v=20261013-asr-5s",
    );
    if (this.cancelled) return;
    this.source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "speech-pcm-capture");
    this.silent = this.context.createGain();
    this.silent.gain.value = 0;
    this.source.connect(this.node);
    this.node.connect(this.silent);
    this.silent.connect(this.context.destination);
    this.node.port.onmessage = ({ data }) => {
      if (data.type === "flushed") this.resolveFlush?.();
      else if (data.type === "chunk" && this.accepting && !this.failed)
        this.enqueue(data.samples, data.offset);
    };
    this.node.onprocessorerror = () => this.fail();
  }
  start() {
    if (!this.node || this.cancelled) return false;
    this.accepting = true;
    this.node.port.postMessage({ type: "start" });
    this.onStatus({ status: "recording", recognized_words: 0 });
    this.pollTimer = setTimeout(() => this.poll(), 2500);
    return true;
  }
  enqueue(samples, offset) {
    if (++this.queued > 4) {
      this.queued--;
      this.fail();
      return;
    }
    const index = this.count++;
    const blob = pcmWav(samples);
    this.chain = this.chain.then(async () => {
      try {
        if (this.cancelled || this.failed) return;
        await this.api.liveChunk(
          this.practiceId,
          blob,
          this.sessionId,
          index,
          offset,
          this.abortController.signal,
        );
      } catch {
        this.fail();
      } finally {
        this.queued--;
      }
    });
  }
  async poll() {
    try {
      if (!this.count || this.failed || this.cancelled) return;
      const status = await this.api.liveTranscript(
        this.practiceId,
        this.sessionId,
        this.abortController.signal,
      );
      if (status.status === "failed" || status.error) this.fail();
      else if (!this.cancelled && !this.failed) this.onStatus(status);
    } catch {
      this.fail();
    } finally {
      if (!this.failed && !this.cancelled && this.accepting)
        this.pollTimer = setTimeout(() => this.poll(), 3000);
    }
  }
  fail() {
    if (this.failed || this.cancelled) return;
    this.failed = true;
    clearTimeout(this.pollTimer);
    this.onStatus({ status: "unavailable" });
  }
  async finish() {
    if (this.cancelled || !this.node || !this.accepting) return null;
    clearTimeout(this.pollTimer);
    const flushed = new Promise((resolve) => {
      this.resolveFlush = resolve;
    });
    this.node.port.postMessage({ type: "flush" });
    const acknowledged = await this.bounded(flushed, 750);
    this.accepting = false;
    const uploaded = acknowledged && (await this.bounded(this.chain, 3000));
    const session =
      uploaded && !this.failed && !this.cancelled && this.count
        ? { sessionId: this.sessionId, chunkCount: this.count }
        : null;
    this.cancel();
    return session;
  }
  async bounded(promise, milliseconds) {
    let timer;
    try {
      return await Promise.race([
        promise.then(() => true),
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(false), milliseconds);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }
  cancel() {
    this.cancelled = true;
    this.accepting = false;
    clearTimeout(this.pollTimer);
    this.abortController.abort();
    this.resolveFlush?.();
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.port.postMessage({ type: "cancel" });
      this.node.disconnect();
    }
    this.source?.disconnect();
    this.silent?.disconnect();
  }
}
