# ADR 010 — Voice agent: Groq Whisper + Piper TTS over WebSocket

- **Status:** Accepted
- **Date:** 2026-06-03

## Context

Weeks 1-3 produced a text agent: cited answers, streaming, conversation memory, eval, observability, caching. Adding voice means routing microphone audio into the existing query pipeline and streaming the cited answer back as synthesized speech.

Two important constraints:

1. **Self-contained on the existing API key.** Adding a second provider for either ASR or TTS (ElevenLabs, OpenAI TTS) introduces a new key, a new bill, and a new failure surface. The user has a Groq key already.
2. **The voice path must reuse Week 1-3 cleanly.** A voice turn is fundamentally a `POST /query` with audio I/O on each side. The agent (`stream_query`), conversation memory, cache, auto-eval, and tracing should all keep working without per-feature special cases.

## Decision

End-to-end voice loop over a WebSocket, using Groq Whisper for ASR and Piper for TTS, with `silero-vad` segmenting utterances and a sentence buffer chunking the streaming LLM output for TTS.

```
Browser                                       FastAPI
  │                                              │
  ├── WS connect /api/v1/voice/stream ─────────▶│
  │   first msg: {jwt, collection_id, conv_id?} │
  │                                             ├── authenticate
  ├── PCM frames (1024 bytes = 512 samp Int16   │
  │   mono @ 16kHz = 32 ms) ───────────────────▶│
  │                                             ├── silero VAD per frame
  │                                             ├── on speech-end + 800ms silence:
  │                                             ├── Groq Whisper transcribe
  │◀── {type:"transcript", text} ───────────────┤
  │                                             ├── stream_query (existing)
  │◀── {type:"agent_token", delta} ─────────────┤
  │                                             ├── sentence boundary detected
  │                                             ├── Piper synthesize_wav
  │◀── audio binary (wav) ──────────────────────┤
  │                                             ├── on agent final
  │◀── {type:"final", citations, query_id} ─────┤
```

### Provider choices

- **ASR: Groq `whisper-large-v3`** — already in the SDK we use, fast (sub-second for short utterances), shares our existing rate-limit quota.
- **TTS: Piper `en_US-amy-medium`, in-process** — Piper is open source, runs in ~real-time on CPU, no API key needed, no per-character cost.

We originally targeted Groq `playai-tts`; mid-build Groq decommissioned it. **No replacement was offered on our tier.** Piper turned out to be the right path anyway — same-process means we don't pay HTTP latency per sentence, and the model (~60MB ONNX) is small enough to keep in a Docker volume.

### Transport: WebSocket

A voice turn is bidirectional and stateful. Pushing 32 ms PCM frames over HTTP request bodies, or making one POST per utterance with the audio buffered client-side, would either delay the start of ASR (high time-to-first-word) or fan out into many connections. A single WS connection per voice session is simpler:

- One TCP + TLS handshake per session.
- Binary frames carry PCM in / WAV out; text frames carry JSON events.
- WS bypasses the existing HTTP middleware stack (different ASGI scope), so we authenticate the JWT manually in the first message rather than via the `AuthMiddleware`.

### Audio format

- **In: 16 kHz mono Int16 PCM, 512 samples (32 ms) per frame.**
  - 16 kHz is Whisper's native rate.
  - Silero VAD v5 requires exactly 512 samples at 16 kHz; we picked the same frame size for the client → no per-frame buffering on the server.
  - The browser AudioWorklet downsamples from the OS-provided 48 kHz.
- **Out: WAV chunks (Piper at 22050 Hz, mono Int16).** Browser decodes via `AudioContext.decodeAudioData` and plays sequentially through `AudioBufferSourceNode`.

### Utterance segmentation

`silero-vad` per frame, then a small state machine (`UtteranceSegmenter`):

- Accumulate speech frames; **in-utterance silence is also accumulated** so Whisper gets continuous audio.
- Close the utterance when `silence_ms` (default 800) consecutive silence frames are observed after `min_utterance_ms` (default 250) of speech.
- Force-close at `max_utterance_ms` (default 30s) to bound buffer growth on an open mic.

### TTS chunking: per sentence

`SentenceBuffer` watches the streaming LLM tokens and emits whole sentences on `.` / `?` / `!`. We synthesize each sentence with Piper and ship the WAV before the LLM has finished the answer. Time-to-first-audio drops from "wait for whole answer" to "wait for first sentence" — a 5× latency improvement on a 200-token response.

The buffer also strips qwen3's `<think>...</think>` reasoning blocks before any boundary detection so they never reach TTS.

## Rationale

- **Why in-process Piper, not a sidecar?** The TTS model is 60 MB and `Piper.synthesize_wav` is sync but bounded — wrapped in `asyncio.to_thread`, it doesn't block the event loop. A sidecar adds an HTTP hop per sentence (≈30 ms each way over local Docker network) and another container to manage. We can extract to a sidecar later if we ever need to scale TTS independently of the API.
- **Why one WS per session instead of one per turn?** Session-level state (which collection, which conversation) doesn't change mid-conversation. Re-establishing the WS + re-resolving the conversation each turn would add ~100 ms of overhead per turn and trigger our rate limit faster.
- **Why per-sentence TTS instead of per-token streaming?** Piper synthesize is one-shot per text input. Token-by-token would require swapping providers for streaming TTS, and the sentence boundary is a natural prosodic break — listeners don't notice the seam between sentences.
- **Why JWT in the first message?** Browsers don't expose `Authorization` headers on WebSocket connects. The options are: query string (visible in server logs, leaks in URLs), cookie (requires same-origin or careful CORS), or first-message handshake. First-message keeps the token off the URL and matches the rest of our auth model.
- **Why bypass the HTTP rate-limit middleware?** It's `BaseHTTPMiddleware` which only fires on HTTP scope. We considered a per-WS per-user concurrent-session cap (3 default) tracked in Redis, but defer it to Week 5; the per-IP TCP socket cap is currently the only backstop.

## Consequences

- **Tracing gained two new spans:** `asr.whisper` (ASR latency, input bytes, output chars) and `tts.piper` (text chars, output bytes). The agent's existing `query` / `retrieve` / `llm.complete` spans still emit unchanged, so a voice turn looks like a normal text turn in Phoenix plus the two voice spans.
- **`services/query_service.stream_query` was refactored.** It previously used `start_as_current_span(...).__enter__()` / `__exit__()` to span the whole generator. Async generators can be iterated from a different asyncio task than the one that created them, which corrupts OTel's `contextvars`-based context stack and breaks the underlying asyncio call chain (we observed real httpx failures during voice turns). Switched to a manual `tracer.start_span("query")` + `finally: span.end()` — the span no longer becomes the parent of child spans automatically, but they still appear at the top level in Phoenix.
- **A 60 MB voice model lives in a Docker volume** (`piper_models`, mounted at `/models/piper`). The model auto-downloads from HuggingFace on first use, so a fresh stack bootstraps without manual steps. The download is one-time per volume — the volume survives container recreations.
- **Memory footprint of the api process grew** by ~250 MB: silero (50 MB), Piper (60 MB) + the runtime tensors, plus sentence-transformers already loaded for the embedder. We hit an OOM kill during dev once with all four model loads + a busy agent invocation; bumping Docker desktop's memory or splitting Piper into a sidecar are options if this becomes routine.
- **Browser mic is 48 kHz; we downsample in an AudioWorklet** (`frontend/public/recorder-worklet.js`). The downsample is a coarse linear interpolation; that's fine for Whisper because the model is trained on telephone-quality audio.
- **TTS audio playback is sequential.** The browser-side `AudioQueue` decodes each WAV chunk and plays it back via `AudioBufferSourceNode.onended`. Total user-perceived latency from speech-end → first audio is ~1.5 s on a warm cache (ASR 400 ms + LLM first-sentence 600 ms + Piper synth 300 ms + browser decode 100 ms + WS latency).

## Out of scope (Week 5)

- **Barge-in:** the server doesn't currently detect new mic activity while it's mid-TTS playback. The first version is strictly turn-taking.
- **Per-token streaming TTS:** would require a different TTS engine (e.g. NVIDIA NeMo TTS, or a custom XTTS sidecar). Sentence-level is good enough for now.
- **Multilingual:** ASR is forced to English (`language="en"`); Piper voice is English. Auto-detect adds eval headache (which voice for what language).
- **Worker-side voice tracing:** the worker doesn't emit voice spans because all voice work happens in the api process. Phoenix worker spans were already deferred in ADR-008.
- **Per-user concurrent-session cap:** would prevent the same user from opening N WS sessions in parallel. Sketched in the original plan, deferred to Week 5.

## Revisit when

- Groq ships streaming TTS (Piper still wins on cost; ship-test against ours).
- We get a paid ElevenLabs key — their voice quality is markedly better, the API is straightforward, and we'd swap Piper for ElevenLabs in `core/voice/tts.py` (~30 lines).
- Barge-in becomes a top user request — at that point the WS protocol needs an explicit "user interrupted" event and the audio queue gets a cancellation hook.
- Voice sessions per user grow past 3-5 concurrent and we need the session cap that's currently deferred.
