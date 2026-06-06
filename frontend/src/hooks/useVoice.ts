"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Citation, getAccessToken } from "@/lib/api";
import { AudioQueue, VoiceCitationData, VoiceClient, VoiceEvent } from "@/lib/voice/client";

function toCitations(raw: VoiceCitationData[]): Citation[] {
  return (raw ?? []).map((c) => ({
    index: c.index,
    preview: c.preview,
    score: c.score ?? 0,
    chunk_id: c.chunk_id ?? "",
    document_id: c.document_id ?? null,
  }));
}

export interface CompletedVoiceTurn {
  transcript: string;
  answer: string;
  citations: Citation[];
  queryId: string;
  intent: string | null;
  latencyMs: number | null;
  cacheHit: boolean;
  cacheHitKind: string | null;
}

export interface LiveVoiceTurn {
  transcript: string;
  partialAnswer: string;
  citations: Citation[];
}

export type VoicePhase = "idle" | "connecting" | "listening" | "answering";

interface UseVoiceArgs {
  collectionId: string | null | undefined;
  conversationId: string;
  onTurnComplete: (turn: CompletedVoiceTurn) => void;
}

export function useVoice({ collectionId, conversationId, onTurnComplete }: UseVoiceArgs) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [liveTurn, setLiveTurn] = useState<LiveVoiceTurn | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clientRef = useRef<VoiceClient | null>(null);
  const queueRef = useRef<AudioQueue | null>(null);
  if (!queueRef.current) {
    queueRef.current = new AudioQueue((playing) => setSpeaking(playing));
  }

  // keep the completion callback current without rebuilding the client
  const onCompleteRef = useRef(onTurnComplete);
  useEffect(() => {
    onCompleteRef.current = onTurnComplete;
  }, [onTurnComplete]);

  const stopSpeaking = useCallback(() => {
    queueRef.current?.cancel();
    clientRef.current?.interrupt();
  }, []);

  const handleEvent = useCallback((ev: VoiceEvent) => {
    switch (ev.type) {
      case "transcript":
        // a new utterance interrupts any audio still playing (barge-in safety net)
        queueRef.current?.cancel();
        clientRef.current?.interrupt();
        setLiveTurn({ transcript: ev.text, partialAnswer: "", citations: [] });
        setPhase("answering");
        break;
      case "agent_token":
        setLiveTurn((t) =>
          t ? { ...t, partialAnswer: t.partialAnswer + ev.delta } : t,
        );
        break;
      case "final":
        setLiveTurn((t) => {
          onCompleteRef.current({
            transcript: t?.transcript ?? "",
            answer: t?.partialAnswer ?? "",
            citations: toCitations(ev.citations),
            queryId: ev.query_id,
            intent: ev.intent ?? null,
            latencyMs: ev.latency_ms ?? null,
            cacheHit: ev.cache_hit ?? false,
            cacheHitKind: ev.cache_hit_kind ?? null,
          });
          return null;
        });
        setPhase("listening");
        break;
      case "cancelled":
        queueRef.current?.cancel();
        break;
      case "error":
        setError(ev.message);
        break;
    }
  }, []);

  const startMic = useCallback(async () => {
    if (!collectionId) {
      setError("This conversation has no collection attached.");
      return;
    }
    const token = getAccessToken();
    if (!token) {
      setError("Not authenticated.");
      return;
    }
    setError(null);
    setPhase("connecting");
    const client = new VoiceClient({
      onEvent: handleEvent,
      onAudio: (wav) => queueRef.current?.enqueue(wav),
      onStateChange: (s) => {
        setRecording(s === "recording");
        if (s === "connected") setPhase((p) => (p === "answering" ? p : "listening"));
        if (s === "closed" || s === "error") {
          setRecording(false);
          setPhase("idle");
        }
      },
    });
    clientRef.current = client;
    try {
      await client.connect(token, collectionId, conversationId);
      await client.startRecording();
      setPhase("listening");
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }, [collectionId, conversationId, handleEvent]);

  const disconnect = useCallback(() => {
    queueRef.current?.cancel();
    clientRef.current?.close();
    clientRef.current = null;
    setRecording(false);
    setSpeaking(false);
    setLiveTurn(null);
    setPhase("idle");
  }, []);

  const stopMic = disconnect;

  // tear down on unmount / conversation switch
  useEffect(() => {
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  return { phase, recording, speaking, liveTurn, error, startMic, stopMic, stopSpeaking, disconnect };
}
