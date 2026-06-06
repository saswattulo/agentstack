"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { getAccessToken, listCollections } from "@/lib/api";
import { AudioQueue, VoiceClient, VoiceEvent, VoiceState } from "@/lib/voice/client";

type Citation = { index: number; preview: string };

export default function VoicePage() {
  const [selected, setSelected] = useState<string>("");
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState<string>("");
  const [answer, setAnswer] = useState<string>("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const clientRef = useRef<VoiceClient | null>(null);
  const queueRef = useRef<AudioQueue>(new AudioQueue());

  const collections = useQuery({ queryKey: ["collections"], queryFn: listCollections });

  useEffect(() => {
    const items = collections.data?.items ?? [];
    if (items[0] && !selected) setSelected(items[0].id);
  }, [collections.data, selected]);

  function onEvent(ev: VoiceEvent) {
    switch (ev.type) {
      case "transcript":
        setTranscript(ev.text);
        setAnswer("");
        setCitations([]);
        break;
      case "agent_token":
        setAnswer((a) => a + ev.delta);
        break;
      case "final":
        setCitations(ev.citations || []);
        break;
      case "cancelled":
        queueRef.current.cancel();
        setAnswer("");
        setCitations([]);
        break;
      case "error":
        setError(ev.message);
        break;
    }
  }

  async function connectAndStart() {
    const token = getAccessToken();
    if (!token || !selected) return;
    setError(null);
    const c = new VoiceClient({
      onEvent,
      onAudio: (wav) => queueRef.current.enqueue(wav),
      onStateChange: setState,
    });
    clientRef.current = c;
    try {
      await c.connect(token, selected);
      await c.startRecording();
    } catch (e) {
      setError(String(e));
    }
  }

  async function stop() {
    await clientRef.current?.stopRecording();
  }

  function disconnect() {
    clientRef.current?.close();
    clientRef.current = null;
    queueRef.current.clear();
    setState("closed");
  }

  const recording = state === "recording";
  const connected = state === "connected" || state === "recording";
  const stripped = answer.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/<think>[\s\S]*$/g, "").trim();

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-1 text-xl font-semibold">Voice agent</h1>
      <p className="mb-4 text-sm text-muted">
        State: <code>{state}</code>. Connect, then speak — the agent answers in voice
        and text. Pause ~800 ms to end your turn. Start talking again to interrupt.
      </p>

      <div className="card mb-4 grid gap-3 p-4">
        <div>
          <label className="mb-1 block text-xs text-muted">Collection</label>
          <select
            className="input"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={connected}
          >
            {(collections.data?.items ?? []).length === 0 && (
              <option value="">No collections</option>
            )}
            {(collections.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-2">
          {!connected && (
            <button className="btn btn-primary" onClick={connectAndStart} disabled={!selected}>
              🎙 Connect &amp; record
            </button>
          )}
          {recording && (
            <button className="btn" onClick={stop}>
              Stop mic
            </button>
          )}
          {connected && !recording && (
            <button className="btn" onClick={() => clientRef.current?.startRecording()}>
              Resume mic
            </button>
          )}
          {connected && (
            <button className="btn btn-danger" onClick={disconnect}>
              Disconnect
            </button>
          )}
        </div>
      </div>

      <section className="grid gap-4">
        <div>
          <h2 className="mb-1 text-sm font-medium text-muted">You said</h2>
          <p className="card min-h-[2.5rem] px-3 py-2 text-sm">
            {transcript || <span className="text-muted">(waiting)</span>}
          </p>
        </div>

        <div>
          <h2 className="mb-1 text-sm font-medium text-muted">Agent</h2>
          <p className="card min-h-[2.5rem] whitespace-pre-wrap px-3 py-2 text-sm">
            {stripped || <span className="text-muted">(waiting)</span>}
          </p>
        </div>

        {citations.length > 0 && (
          <div>
            <h2 className="mb-1 text-sm font-medium text-muted">Citations</h2>
            <ul className="grid gap-1">
              {citations.map((c) => (
                <li key={c.index} className="card px-3 py-2 text-xs text-muted">
                  <code className="text-accent">[{c.index}]</code> {c.preview}
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && <p className="text-sm text-danger">error: {error}</p>}
      </section>
    </div>
  );
}
