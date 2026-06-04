// Audio worklet that downsamples the browser's mic stream (usually 48 kHz)
// to 16 kHz mono Int16 and posts 512-sample (32 ms) frames to the main thread.
//
// This file is loaded via `audioContext.audioWorklet.addModule()` so the
// compiled JS is what runs in the worklet thread — Next.js must serve it from
// /public. We export it as a string from a sibling .ts file and write it out
// at runtime; or — simpler for now — we author it as a plain .js in /public.
//
// This file is here for type-checking only. The actual runtime is
// `frontend/public/recorder-worklet.js`. Keep them in sync.

class RecorderWorklet extends AudioWorkletProcessor {
  private buffer: Float32Array = new Float32Array(0);
  private downsampleRatio: number = 1;
  private outputSize: number = 512; // 32 ms @ 16 kHz

  constructor() {
    super();
    this.downsampleRatio = sampleRate / 16000;
  }

  process(inputs: Float32Array[][]): boolean {
    const input = inputs[0]?.[0];
    if (!input) return true;
    const merged = new Float32Array(this.buffer.length + input.length);
    merged.set(this.buffer);
    merged.set(input, this.buffer.length);
    this.buffer = merged;

    const downsampledLen = Math.floor(this.buffer.length / this.downsampleRatio);
    if (downsampledLen >= this.outputSize) {
      const out = new Int16Array(this.outputSize);
      for (let i = 0; i < this.outputSize; i++) {
        const idx = Math.floor(i * this.downsampleRatio);
        const sample = Math.max(-1, Math.min(1, this.buffer[idx]));
        out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      const consumed = Math.floor(this.outputSize * this.downsampleRatio);
      this.buffer = this.buffer.slice(consumed);
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}

registerProcessor("recorder-worklet", RecorderWorklet);

declare const sampleRate: number;
declare class AudioWorkletProcessor {
  port: MessagePort;
  constructor();
  process(inputs: Float32Array[][]): boolean;
}
declare function registerProcessor(name: string, processor: typeof AudioWorkletProcessor): void;
