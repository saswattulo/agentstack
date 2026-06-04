"use client";

import { useEffect, useRef, useState } from "react";
import {
  Collection,
  getAccessToken,
  listCollections,
  login,
} from "@/lib/api";
import { AudioQueue, VoiceClient, VoiceEvent, VoiceState } from "@/lib/voice/client";

type Citation = { index: number; preview: string };

export default function VoicePage() {
  const [token, setToken] = useState<string | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState<string>("");
  const [answer, setAnswer] = useState<string>("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const clientRef = useRef<VoiceClient | null>(null);
  const queueRef = useRef<AudioQueue>(new AudioQueue());

  // Boot: if we have a JWT, fetch collections.
  useEffect(() => {
    const t = getAccessToken();
    if (t) {
      setToken(t);
      listCollections()
        .then((d) => {
          setCollections(d.items);
          if (d.items[0]) setSelected(d.items[0].id);
        })
        .catch((e) => setError(String(e)));
    }
  }, []);

  async function handleLogin(form: FormData) {
    try {
      const res = await login(
        String(form.get("email") || ""),
        String(form.get("password") || ""),
      );
      setToken(res.access_token);
      const list = await listCollections();
      setCollections(list.items);
      if (list.items[0]) setSelected(list.items[0].id);
    } catch (e) {
      setError(String(e));
    }
  }

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
      case "error":
        setError(ev.message);
        break;
    }
  }

  async function connectAndStart() {
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

  if (!token) {
    return (
      <main style={pageStyle}>
        <h1>Voice agent</h1>
        <p>Log in to continue.</p>
        <form
          action={handleLogin}
          style={{ display: "grid", gap: "0.5rem", maxWidth: 320 }}
        >
          <input name="email" type="email" placeholder="email" required />
          <input name="password" type="password" placeholder="password" required />
          <button type="submit">Log in</button>
        </form>
        {error && <p style={{ color: "salmon" }}>{error}</p>}
      </main>
    );
  }

  const recording = state === "recording";
  const connected = state === "connected" || state === "recording";

  return (
    <main style={pageStyle}>
      <h1>Voice agent</h1>
      <p style={{ opacity: 0.7, fontSize: 14 }}>
        State: <code>{state}</code>. Click <em>Connect & record</em>, then speak.
        The agent answers in voice and text. Pause ~800 ms to end your turn.
      </p>

      <section style={{ marginTop: "1rem", display: "grid", gap: "0.75rem" }}>
        <label>
          Collection
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={connected}
            style={{ width: "100%", padding: "0.5rem" }}
          >
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <div style={{ display: "flex", gap: "0.5rem" }}>
          {!connected && (
            <button onClick={connectAndStart} disabled={!selected}>
              Connect &amp; record
            </button>
          )}
          {recording && <button onClick={stop}>Stop mic</button>}
          {connected && !recording && (
            <button onClick={() => clientRef.current?.startRecording()}>
              Resume mic
            </button>
          )}
          {connected && <button onClick={disconnect}>Disconnect</button>}
        </div>
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>You said</h2>
        <p style={transcriptStyle}>{transcript || <em style={{ opacity: 0.5 }}>(waiting)</em>}</p>

        <h2 style={{ margin: 0, fontSize: 18, marginTop: "1rem" }}>Agent</h2>
        <p style={answerStyle}>{answer || <em style={{ opacity: 0.5 }}>(waiting)</em>}</p>

        {citations.length > 0 && (
          <div style={{ marginTop: "0.75rem" }}>
            <strong>Citations:</strong>
            <ul>
              {citations.map((c) => (
                <li key={c.index}>
                  <code>[{c.index}]</code> {c.preview}
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && (
          <p style={{ color: "salmon", marginTop: "1rem" }}>error: {error}</p>
        )}
      </section>
    </main>
  );
}

const pageStyle: React.CSSProperties = {
  padding: "2rem",
  maxWidth: 800,
  margin: "0 auto",
};

const transcriptStyle: React.CSSProperties = {
  background: "#1f2937",
  padding: "0.75rem 1rem",
  borderRadius: 8,
  minHeight: "2.5rem",
};

const answerStyle: React.CSSProperties = {
  background: "#111827",
  padding: "0.75rem 1rem",
  borderRadius: 8,
  minHeight: "2.5rem",
  whiteSpace: "pre-wrap",
};
