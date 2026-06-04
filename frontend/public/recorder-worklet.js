// Mic downsampler. Browser delivers 48 kHz Float32; we emit 16 kHz Int16
// PCM in 512-sample (32 ms) frames so the server-side silero VAD can
// classify each frame directly.

class RecorderWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._ratio = sampleRate / 16000;
    this._outputSize = 512;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;

    const merged = new Float32Array(this._buffer.length + input.length);
    merged.set(this._buffer);
    merged.set(input, this._buffer.length);
    this._buffer = merged;

    while (Math.floor(this._buffer.length / this._ratio) >= this._outputSize) {
      const out = new Int16Array(this._outputSize);
      for (let i = 0; i < this._outputSize; i++) {
        const idx = Math.floor(i * this._ratio);
        const s = Math.max(-1, Math.min(1, this._buffer[idx]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      const consumed = Math.floor(this._outputSize * this._ratio);
      this._buffer = this._buffer.slice(consumed);
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}

registerProcessor("recorder-worklet", RecorderWorklet);
