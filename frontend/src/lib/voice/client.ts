// VoiceClient — manages the WebSocket to /api/v1/voice/stream, the mic
// AudioWorklet, and an audio playback queue for the server-side TTS.

export type VoiceEvent =
  | { type: "ready"; sample_rate: number; frame_bytes: number; conversation_id: string }
  | { type: "transcript"; text: string }
  | { type: "agent_token"; delta: string }
  | { type: "final"; query_id: string; intent: string; citations: { index: number; preview: string }[]; latency_ms: number; cache_hit?: boolean }
  | { type: "error"; message: string }
  | { type: "pong" };

export interface VoiceClientHandlers {
  onEvent: (event: VoiceEvent) => void;
  onAudio: (wav: ArrayBuffer) => void;
  onStateChange?: (state: VoiceState) => void;
}

export type VoiceState = "idle" | "connecting" | "connected" | "recording" | "closed" | "error";

const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class VoiceClient {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private micStream: MediaStream | null = null;
  private state: VoiceState = "idle";

  constructor(private handlers: VoiceClientHandlers) {}

  private setState(s: VoiceState) {
    this.state = s;
    this.handlers.onStateChange?.(s);
  }

  async connect(jwt: string, collectionId: string, conversationId?: string): Promise<void> {
    this.setState("connecting");
    const url = `${PUBLIC_API.replace(/^http/, "ws")}/api/v1/voice/stream`;
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "init",
            jwt,
            collection_id: collectionId,
            ...(conversationId ? { conversation_id: conversationId } : {}),
          }),
        );
      };

      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          this.handlers.onAudio(ev.data);
          return;
        }
        try {
          const event = JSON.parse(ev.data) as VoiceEvent;
          if (event.type === "ready") {
            this.setState("connected");
            resolve();
          }
          this.handlers.onEvent(event);
        } catch {
          // ignore malformed
        }
      };

      ws.onerror = () => {
        this.setState("error");
        reject(new Error("websocket error"));
      };

      ws.onclose = () => {
        this.setState("closed");
      };

      this.ws = ws;
    });
  }

  async startRecording(): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("connect first");
    }
    if (this.workletNode) return; // already recording

    const ctx = new AudioContext({ sampleRate: 48000 });
    await ctx.audioWorklet.addModule("/recorder-worklet.js");

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const source = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, "recorder-worklet");
    node.port.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(ev.data);
      }
    };
    source.connect(node);
    // do NOT connect node → destination (we don't want loopback playback)

    this.ctx = ctx;
    this.workletNode = node;
    this.micStream = stream;
    this.setState("recording");
  }

  async stopRecording(): Promise<void> {
    this.workletNode?.disconnect();
    this.workletNode = null;
    this.micStream?.getTracks().forEach((t) => t.stop());
    this.micStream = null;
    await this.ctx?.close();
    this.ctx = null;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.setState("connected");
    }
  }

  close(): void {
    this.stopRecording();
    this.ws?.close();
    this.ws = null;
  }
}

// Sequential WAV playback queue.
export class AudioQueue {
  private ctx: AudioContext | null = null;
  private playing = false;
  private q: ArrayBuffer[] = [];

  enqueue(wav: ArrayBuffer) {
    this.q.push(wav);
    if (!this.playing) void this.drain();
  }

  clear() {
    this.q = [];
  }

  private async drain() {
    this.playing = true;
    if (!this.ctx) this.ctx = new AudioContext();
    while (this.q.length) {
      const wav = this.q.shift()!;
      try {
        const buf = await this.ctx.decodeAudioData(wav.slice(0));
        await new Promise<void>((resolve) => {
          const src = this.ctx!.createBufferSource();
          src.buffer = buf;
          src.connect(this.ctx!.destination);
          src.onended = () => resolve();
          src.start();
        });
      } catch (e) {
        // skip malformed chunk
        console.error("audio decode failed", e);
      }
    }
    this.playing = false;
  }
}
