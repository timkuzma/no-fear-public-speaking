import { PCMChunker } from "./live-audio.js?v=20261011-live";
class SpeechPCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = false;
    this.chunker = new PCMChunker(sampleRate, 16000, 15, (samples, offset) => {
      this.port.postMessage({ type: "chunk", samples, offset }, [
        samples.buffer,
      ]);
    });
    this.port.onmessage = ({ data }) => {
      if (data.type === "start") {
        this.chunker.reset();
        this.active = true;
      } else if (data.type === "flush") {
        this.active = false;
        this.chunker.flush();
        this.port.postMessage({ type: "flushed" });
      } else if (data.type === "cancel") this.active = false;
    };
  }
  process(inputs) {
    if (this.active && inputs[0]?.length) this.chunker.push(inputs[0]);
    return true;
  }
}
registerProcessor("speech-pcm-capture", SpeechPCMCapture);
