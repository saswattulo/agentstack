"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatComposer } from "@/components/ChatComposer";
import { ChatMessage, MessageBubble } from "@/components/MessageBubble";
import { getConversation } from "@/lib/api";
import { useStreamingQuery } from "@/hooks/useStreamingQuery";
import { CompletedVoiceTurn, useVoice } from "@/hooks/useVoice";

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const qc = useQueryClient();
  const { state, send, reset } = useStreamingQuery();

  // live (this-session) messages layered on top of the persisted history
  const [live, setLive] = useState<ChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const conv = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => getConversation(conversationId),
  });
  const collectionId = conv.data?.collection_id;

  // voice: a completed spoken turn becomes the same user+assistant bubbles as text
  const onVoiceComplete = useCallback(
    (turn: CompletedVoiceTurn) => {
      setLive((l) => [
        ...l,
        { role: "user", content: turn.transcript },
        {
          role: "assistant",
          content: turn.answer,
          citations: turn.citations,
          queryId: turn.queryId,
          intent: turn.intent,
          latencyMs: turn.latencyMs,
          cacheHit: turn.cacheHit,
          cacheHitKind: turn.cacheHitKind,
        },
      ]);
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    [qc],
  );

  const voice = useVoice({
    collectionId,
    conversationId,
    onTurnComplete: onVoiceComplete,
  });

  // reset live layer when switching conversations
  useEffect(() => {
    setLive([]);
  }, [conversationId]);

  const persisted: ChatMessage[] = useMemo(() => {
    const out: ChatMessage[] = [];
    for (const m of conv.data?.messages ?? []) {
      out.push({ role: "user", content: m.question });
      if (m.answer) {
        out.push({
          role: "assistant",
          content: m.answer,
          citations: m.citations,
          queryId: m.query_id,
        });
      }
    }
    return out;
  }, [conv.data]);

  // full visible list: history + committed live turns + whichever turn is in-flight
  const messages = useMemo(() => {
    const all = [...persisted, ...live];

    // text in-flight (typed question)
    if (state.streaming || state.status || state.partialAnswer) {
      all.push({
        role: "assistant",
        content: state.partialAnswer,
        citations: state.citations,
        status: state.status,
        streaming: state.streaming,
      });
    }

    // voice in-flight (spoken question): show the transcript + streaming answer
    if (voice.liveTurn) {
      all.push({ role: "user", content: voice.liveTurn.transcript });
      all.push({
        role: "assistant",
        content: voice.liveTurn.partialAnswer,
        citations: voice.liveTurn.citations,
        status: voice.liveTurn.partialAnswer ? null : "thinking…",
        streaming: true,
      });
    }

    return all;
  }, [persisted, live, state, voice.liveTurn]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, state.partialAnswer, voice.liveTurn?.partialAnswer]);

  async function onSend(text: string) {
    if (!collectionId) {
      alert("This conversation has no collection attached.");
      return;
    }
    setLive((l) => [...l, { role: "user", content: text }]);

    const final = await send({
      collection_id: collectionId,
      question: text,
      conversation_id: conversationId,
    });

    if (final) {
      setLive((l) => [
        ...l,
        {
          role: "assistant",
          content: final.answer,
          citations: final.citations,
          queryId: final.query_id,
          intent: final.intent,
          toolsUsed: final.tools_used,
          cacheHit: final.cache_hit,
          cacheHitKind: final.cache_hit_kind,
          latencyMs: final.latency_ms,
        },
      ]);
      reset();
      qc.invalidateQueries({ queryKey: ["conversations"] });
    }
  }

  const micActive = voice.recording || voice.phase === "connecting";

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-2">
        <h2 className="truncate text-sm font-medium">{conv.data?.title ?? "…"}</h2>
        {(voice.recording || voice.speaking || voice.phase !== "idle") && (
          <span className="chip">
            {voice.speaking ? "🔊 speaking" : voice.recording ? "🎙 listening" : voice.phase}
          </span>
        )}
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
          {conv.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} />
          ))}
          {(state.error || voice.error) && (
            <p className="text-sm text-danger">error: {state.error || voice.error}</p>
          )}
        </div>
      </div>

      <ChatComposer
        onSend={onSend}
        disabled={state.streaming}
        recording={micActive}
        speaking={voice.speaking}
        onMicToggle={voice.recording ? voice.stopMic : voice.startMic}
        onStopSpeaking={voice.stopSpeaking}
      />
    </div>
  );
}
