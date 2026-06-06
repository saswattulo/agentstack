"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChatComposer } from "@/components/ChatComposer";
import { ChatMessage, MessageBubble } from "@/components/MessageBubble";
import { getConversation } from "@/lib/api";
import { useStreamingQuery } from "@/hooks/useStreamingQuery";

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
          // cacheHit unknown for history; hide eval badge re-poll noise by
          // treating history answers as already-scored (queryId still set,
          // EvalBadge will fetch existing result once).
        });
      }
    }
    return out;
  }, [conv.data]);

  // assemble the full visible list: persisted history + live turns
  const messages = useMemo(() => {
    const all = [...persisted, ...live];
    if (state.streaming || state.status || state.partialAnswer) {
      // the in-flight assistant bubble (its paired user bubble is already in `live`)
      all.push({
        role: "assistant",
        content: state.partialAnswer,
        citations: state.citations,
        status: state.status,
        streaming: state.streaming,
      });
    }
    return all;
  }, [persisted, live, state]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, state.partialAnswer]);

  async function onSend(text: string) {
    const collectionId = conv.data?.collection_id;
    if (!collectionId) {
      alert("This conversation has no collection attached.");
      return;
    }
    // optimistic user bubble
    setLive((l) => [...l, { role: "user", content: text }]);

    const final = await send({
      collection_id: collectionId,
      question: text,
      conversation_id: conversationId,
    });

    if (final) {
      // commit the completed assistant turn into the live layer, then clear
      // the streaming state so the in-flight bubble doesn't duplicate it
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
          latencyMs: final.latency_ms,
        },
      ]);
      reset();
      // refresh the conversation list (updated_at ordering)
      qc.invalidateQueries({ queryKey: ["conversations"] });
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b border-border bg-surface px-4 py-2">
        <h2 className="truncate text-sm font-medium">{conv.data?.title ?? "…"}</h2>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
          {conv.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} />
          ))}
          {state.error && (
            <p className="text-sm text-danger">error: {state.error}</p>
          )}
        </div>
      </div>

      <ChatComposer onSend={onSend} disabled={state.streaming} />
    </div>
  );
}
