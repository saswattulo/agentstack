"use client";

import { Citation } from "@/lib/api";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { EvalBadge } from "./EvalBadge";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  queryId?: string;
  intent?: string | null;
  toolsUsed?: string[];
  cacheHit?: boolean;
  latencyMs?: number | null;
  streaming?: boolean;
  status?: string | null;
}

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent/15 px-3 py-2 text-sm">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[85%]">
        <div className="card px-3 py-2 text-sm">
          {msg.status && !msg.content && (
            <span className="text-muted">{msg.status}</span>
          )}
          {msg.content && (
            <AnswerMarkdown text={msg.content} citations={msg.citations ?? []} />
          )}
          {msg.streaming && msg.content && (
            <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-accent align-middle" />
          )}
        </div>

        {!msg.streaming && (msg.queryId || msg.intent) && (
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {msg.intent && <span className="chip">{msg.intent}</span>}
            {msg.cacheHit && <span className="chip text-ok">cache hit</span>}
            {msg.toolsUsed?.map((t) => (
              <span key={t} className="chip">
                {t}
              </span>
            ))}
            {msg.latencyMs != null && (
              <span className="chip">{(msg.latencyMs / 1000).toFixed(1)}s</span>
            )}
          </div>
        )}

        {msg.queryId && !msg.cacheHit && <EvalBadge queryId={msg.queryId} />}
      </div>
    </div>
  );
}
